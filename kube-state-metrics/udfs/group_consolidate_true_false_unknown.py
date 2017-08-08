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

    def process(self, target_tag, true_value, false_value, unknown_value):
        if self._points:
            # Of the targeted entries, only one should have a non-zero value. Get this one.
            flagged_entries = [entry for entry in self._points if entry.fieldsDouble['value']]
            if len(flagged_entries) != 1:
                logger.error("Clear target data not detected, found: %r" % flagged_entries)

            # Set the value of the entry to a true/false/unknown value, based on the value of the target tag.
            self._consolidated_point = flagged_entries[0]
            condition = self._consolidated_point.tags.pop(target_tag)
            if condition == 'true':
                self._consolidated_point.fieldsDouble['value'] = float(true_value)
            elif condition == 'false':
                self._consolidated_point.fieldsDouble['value'] = float(false_value)
            elif condition == 'unknown':
                self._consolidated_point.fieldsDouble['value'] = float(unknown_value)


class KubeStateMetricsConsolidateTrueFalseUnknown(Handler):

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

        self._measurement = None
        self._tag = None
        self._true_value = None
        self._false_value = None
        self._unknown_value = None

        self._begin_response = None
        self._state = KubeStateMetricsConsolidateTrueFalseUnknown.state()

    def info(self):
        response = udf_pb2.Response()
        response.info.wants = udf_pb2.STREAM
        response.info.provides = udf_pb2.STREAM
        response.info.options['measurement'].valueTypes.append(udf_pb2.STRING)
        response.info.options['tag'].valueTypes.append(udf_pb2.STRING)
        response.info.options['trueValue'].valueTypes.append(udf_pb2.INT)
        response.info.options['falseValue'].valueTypes.append(udf_pb2.INT)
        response.info.options['unknownValue'].valueTypes.append(udf_pb2.INT)
        return response

    def init(self, init_req):
        success = True
        msg = ''

        for opt in init_req.options:
            if opt.name == 'measurement':
                self._measurement = opt.values[0].stringValue
            elif opt.name == 'tag':
                self._tag = opt.values[0].stringValue
            elif opt.name == 'trueValue':
                self._true_value = opt.values[0].intValue
            elif opt.name == 'falseValue':
                self._false_value = opt.values[0].intValue
            elif opt.name == 'unknownValue':
                self._unknown_value = opt.values[0].intValue

        if not self._measurement:
            success = False
            msg += ' must supply measurement'
        if not self._tag:
            success = False
            msg += ' must supply tag'
        if self._true_value == None:
            success = False
            msg += ' must supply trueValue'
        if self._false_value == None:
            success = False
            msg += ' must supply falseValue'
        if self._unknown_value == None:
            success = False
            msg += ' must supply unknownValue'

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
        self._state.process(self._tag, self._true_value, self._false_value, self._unknown_value)

        for group_id, group_buffer in self._state.group_buffers.items():
            if group_buffer._consolidated_point:
                response = udf_pb2.Response()
                response.point.CopyFrom(group_buffer._consolidated_point)
                self._agent.write_response(response)

        self._state.reset()

    def point(self, point):
        # Points come through in bursts, all from a particular scrape share the same time.
        # So once the time changes, we can flush the current cache.
        if self._state.time and self._state.time != point.time:
            self.flush()

        # If the point is from a relevant measurement, cache it; otherwise just pass it through.
        #   (This is particularly useful if such UDFs exist in a chain, to avoid a cache sequence that
        #    requires N time changes in order to fully propagate through N nodes.)
        if point.tags['__name__'] == self._measurement:
           self._state.update(point)
        else:
           response = udf_pb2.Response()
           response.point.CopyFrom(point)
           self._agent.write_response(response)


if __name__ == '__main__':
    agent = Agent()
    handler = KubeStateMetricsConsolidateTrueFalseUnknown(agent)
    agent.handler = handler
    logger.info("Starting agent")
    agent.start()
    agent.wait()
    logger.info("Agent finished")

