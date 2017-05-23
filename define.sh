#!/bin/bash

set -e

kapacitor define-template normalize-node_exporter -type stream -tick normalize-node_exporter.tmpl.tick
kapacitor define node_exporter-influxdb-out -type stream -tick influxdb_out.tick -dbrp prometheus.autogen
kapacitor enable node_exporter-influxdb-out

for f in measurements/*.json
do
    name=$(basename $f)
    name=${name/.json/}
    kapacitor define normalize-$name \
        -template normalize-node_exporter \
        -dbrp prometheus_raw.autogen \
        -vars $f
    kapacitor enable normalize-$name
done
