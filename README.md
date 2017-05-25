# Prometheus Metric Normalizer

This repo contains a shell script for defining tasks on kapacitor that normalize metrics coming from prometheus scraping.

### normalize-prometheus.tmpl.tick

This is a [templated tick script](https://docs.influxdata.com/kapacitor/v1.3/guides/template_tasks/) that handles the data in the `prometheus_raw` database, converts it to the InfluxDB format, and outputs it back to kapacitor in the `prometheus` database.

### `{{ .Folder }}` - kubernetes, nginx, etc...

Each folder contains `.json` files that represent different instances of the `normalize-prometheus.tmpl.tick` script.

### prometheus-out.tick

This tick script takes the data coming into kapacitor from the `normalize-prometheus.tmpl.tick` tasks and outputs it to the configured InfluxDB instance.

### define.sh

A shell script that defines and enables all of the template tasks in a folder. It takes the folder name without a `/` as an argument.

