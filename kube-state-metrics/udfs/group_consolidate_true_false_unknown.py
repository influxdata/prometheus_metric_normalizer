import sys
from kapacitor.udf.agent import Agent, Handler, Server
from kapacitor.udf import udf_pb2

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger()

class KubeStateMetricsConsolidateTrueFalseUnknown(Handler):

    class state(object):
        def __init__(self):
            self._entries = []

        def reset(self):
            self._entries = []

        def update(self, point):
            #print >> sys.stderr, ("POINT: %r" % point)
            self._entries.append(point)

        def process(self, target_measurement, target_tag, true_value, false_value, unknown_value):
            target_entries = []
            other_entries = []

            for entry in self._entries:
                if entry.tags['__name__'] == target_measurement:
                    target_entries.append(entry)
                else:
                    other_entries.append(entry)

            if target_entries:
                flagged_entries = [entry for entry in target_entries if entry.fieldsDouble['value']]
                if len(flagged_entries) != 1:
                    logger.error("Clear target data not detected, found: %r" % flagged_entries)

                flagged_entry = flagged_entries[0]
                condition = flagged_entry.tags.pop(target_tag)
                if condition == 'true':
                    flagged_entry.fieldsDouble['value'] = float(true_value)
                elif condition == 'false':
                    flagged_entry.fieldsDouble['value'] = float(false_value)
                elif condition == 'unknown':
                    flagged_entry.fieldsDouble['value'] = float(unknown_value)

                other_entries.append(flagged_entry)

            self._entries = other_entries


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
        response.info.wants = udf_pb2.BATCH
        response.info.provides = udf_pb2.BATCH
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
        self._state.reset()
        # Keep copy of begin_batch
        response = udf_pb2.Response()
        response.begin.CopyFrom(begin_req)
        self._begin_response = response

    def end_batch(self, end_req):
        self._state.process(self._measurement, self._tag, self._true_value, self._false_value, self._unknown_value)

        # Send begin batch with count of outliers
        self._begin_response.begin.size = len(self._state._entries)
        self._agent.write_response(self._begin_response)

        response = udf_pb2.Response()
        for entry in self._state._entries:
            response.point.CopyFrom(entry)
            self._agent.write_response(response)

        # Send an identical end batch back to Kapacitor
        response.end.CopyFrom(end_req)
        self._agent.write_response(response)

    def point(self, point):
        self._state.update(point)


if __name__ == '__main__':
    agent = Agent()
    handler = KubeStateMetricsConsolidateTrueFalseUnknown(agent)
    agent.handler = handler
    logger.info("Starting agent")
    agent.start()
    agent.wait()
    logger.info("Agent finished")

