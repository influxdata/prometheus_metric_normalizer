#!/bin/bash

set -e

source=$1

[ -z "$source" ] && echo "Need to pass source as arg..." && exit 1;

kapacitor define prometheus-out -type stream -tick prometheus-out.tick -dbrp prometheus.autogen
kapacitor enable prometheus-out

if [ "$source" == "kube-state-metrics" ]; then

    echo "== NOTE =="
    echo "kube-state-metrics normalization involves custom UDFs."
    echo "Be sure you've defined said UDFs in your kapacitor config -- see ./kube-state-metrics/config/kapacitor.conf for reference."

    for f in $source/ticks/*
    do
        name=$(basename $f)
        name=${name/.json/}
        kapacitor define normalize-$source-$name \
            -dbrp prometheus_raw.autogen \
            -type stream \
            -tick $f
        kapacitor enable normalize-$source-$name
    done

else

    kapacitor define-template normalize-prometheus -type stream -tick normalize-prometheus.tmpl.tick

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

fi
