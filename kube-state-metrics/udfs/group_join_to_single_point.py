import sys
from kapacitor.udf.agent import Agent, Handler, Server
from kapacitor.udf import udf_pb2

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger()


class GroupBuffer(object):

    def __init__(self):
        self._points = []

    def append(self, point):
        self._points.append(point)

    def process(self, strip_prefix, drop_tags, ignore_values_from):
        self._fields = {}
        self._tags = {}

        for entry in self._points:
            entry_name = entry.tags['__name__']

            if entry_name not in ignore_values_from:
                if strip_prefix and entry_name.startswith(strip_prefix):
                    entry_name = entry_name[len(strip_prefix):]

                self._fields[entry_name] = entry.fieldsDouble['value']

            for tag,value in entry.tags.items():
                if tag not in drop_tags:
                    self._tags[tag] = value

        if not self._fields:
            # There has to be at least one field in order for influxdb to accept the series.
            self._fields = { 'unused_field': 1 }


class KubeStateMetricsJoinToSinglePoint(Handler):

    class state(object):
        def __init__(self):
            self.time = None
            self.group_buffers = {}

        def update(self, point):
            #print >> sys.stderr, ("POINT: %r" % point)
            if not self.time:
                self.time = point.time
            group_buffer = self.group_buffers.get(point.group, GroupBuffer())
            group_buffer.append(point)
            self.group_buffers[point.group] = group_buffer

        def process(self, *args, **kwargs):
            for group_buffer in self.group_buffers.values():
                group_buffer.process(*args, **kwargs)

        def reset(self):
            self.time = None
            self.group_buffers.clear()


    def __init__(self, agent):
        self._agent = agent

        self._strip_prefix = None
        self._drop_tags = []
        self._ignore_values_from = []

        self._begin_response = None
        self._state = KubeStateMetricsJoinToSinglePoint.state()

    def info(self):
        response = udf_pb2.Response()
        response.info.wants = udf_pb2.STREAM
        response.info.provides = udf_pb2.STREAM
        response.info.options['stripPrefix'].valueTypes.append(udf_pb2.STRING)
        response.info.options['dropTag'].valueTypes.append(udf_pb2.STRING)
        response.info.options['ignoreValueFrom'].valueTypes.append(udf_pb2.STRING)
        return response

    def init(self, init_req):
        success = True
        msg = ''

        for opt in init_req.options:
            if opt.name == 'stripPrefix':
                self._strip_prefix = opt.values[0].stringValue
            elif opt.name == 'dropTag':
                self._drop_tags.append(opt.values[0].stringValue)
            elif opt.name == 'ignoreValueFrom':
                self._ignore_values_from.append(opt.values[0].stringValue)

        response = udf_pb2.Response()
        response.init.success = success
        response.init.error = msg[1:]

        return response

    def snapshot(self):
        response = udf_pb2.Response()
        response.snapshot.snapshot = ''
        return response

    def restore(self, restore_req):
        response = udf_pb2.Response()
        response.restore.success = False
        response.restore.error = 'not implemented'
        return response

    def begin_batch(self, begin_req):
        raise Exception("not supported")

    def end_batch(self, end_req):
        raise Exception("not supported")

    def flush(self):
        self._state.process(self._strip_prefix, self._drop_tags, self._ignore_values_from)

        for group_id, group_buffer in self._state.group_buffers.items():
            response = udf_pb2.Response()
            response.point.group = group_id
            response.point.time = self._state.time

            for tag,value in group_buffer._tags.items():
                response.point.tags[tag] = value

            for field,value in group_buffer._fields.items():
                response.point.fieldsDouble[field] = value

            self._agent.write_response(response)

        self._state.reset()

    def point(self, point):
        # Points come through in bursts, all from a particular scrape share the same time.
        # So once the time changes, we can flush the current cache.
        if self._state.time and self._state.time != point.time:
            self.flush()

        # Add point to cache.
        self._state.update(point)


if __name__ == '__main__':
    agent = Agent()
    handler = KubeStateMetricsJoinToSinglePoint(agent)
    agent.handler = handler
    logger.info("Starting agent")
    agent.start()
    agent.wait()
    logger.info("Agent finished")

