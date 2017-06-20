import sys
from kapacitor.udf.agent import Agent, Handler, Server
from kapacitor.udf import udf_pb2

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger()

class KubeStateMetricsJoinToSinglePoint(Handler):

    class state(object):
        def __init__(self):
            self._entries = []

        def reset(self):
            self._entries = []

        def update(self, point):
            #print >> sys.stderr, ("POINT: %r" % point)
            self._entries.append(point)

        def process(self, strip_prefix, drop_tags, ignore_values_from):
            all_data = {}

            for entry in self._entries:
                data = all_data.get(entry.time, {})

                entry_name = entry.tags['__name__']

                if entry_name not in ignore_values_from:
                    fields = data.get('fields', {})

                    if strip_prefix and entry_name.startswith(strip_prefix):
                        entry_name = entry_name[len(strip_prefix):]

                    fields[entry_name] = entry.fieldsDouble['value']
                    data['fields'] = fields

                tags = data.get('tags', {})
                for tag,value in entry.tags.items():
                    if tag not in drop_tags:
                        tags[tag] = value
                data['tags'] = tags

                all_data[entry.time] = data

            if not all_data:
                logger.error("No data available to join.")
            elif len(all_data) > 1:
                logger.error("Multiple times present in dataset: %r" % all_data)

            time = all_data.keys()[0]

            self._time = time
            self._tags = all_data[time].get('tags', {})
            self._fields = all_data[time].get('fields', {})

            if not self._fields:
                # There has to be at least one field in order for influxdb to accept the series.
                self._fields = { 'unused_field': 1 }

    def __init__(self, agent):
        self._agent = agent

        self._strip_prefix = None
        self._drop_tags = []
        self._ignore_values_from = []

        self._begin_response = None
        self._state = KubeStateMetricsJoinToSinglePoint.state()

    def info(self):
        response = udf_pb2.Response()
        response.info.wants = udf_pb2.BATCH
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
        self._state.reset()

    def end_batch(self, end_req):
        self._state.process(self._strip_prefix, self._drop_tags, self._ignore_values_from)

        response = udf_pb2.Response()
        response.point.group = end_req.group

        response.point.time = self._state._time

        for tag,value in self._state._tags.items():
            response.point.tags[tag] = value

        for field,value in self._state._fields.items():
            response.point.fieldsDouble[field] = value

        self._agent.write_response(response)

    def point(self, point):
        self._state.update(point)


if __name__ == '__main__':
    agent = Agent()
    handler = KubeStateMetricsJoinToSinglePoint(agent)
    agent.handler = handler
    logger.info("Starting agent")
    agent.start()
    agent.wait()
    logger.info("Agent finished")

