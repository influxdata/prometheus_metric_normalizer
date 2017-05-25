#!/bin/bash

set -e

source=$1

[ -z "$source" ] && echo "Need to pass source as arg..." && exit 1;

kapacitor define-template normalize-prometheus -type stream -tick normalize-prometheus.tmpl.tick
kapacitor define prometheus-out -type stream -tick prometheus-out.tick -dbrp prometheus.autogen
kapacitor enable prometheus-out

for f in $source/*.json
do
    name=$(basename $f)
    name=${name/.json/}
    kapacitor define normalize-$source-$name \
        -template normalize-prometheus \
        -dbrp prometheus_raw.autogen \
        -vars $f
    kapacitor enable normalize-$source-$name
done