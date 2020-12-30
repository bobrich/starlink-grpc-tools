#!/usr/bin/python3
######################################################################
#
# Write get_status info to an InfluxDB database.
#
# This script will periodically poll current status and write it to
# the specified InfluxDB database in a loop.
#
######################################################################
from influxdb import InfluxDBClient
from influxdb import SeriesHelper

import grpc

import spacex.api.device.device_pb2
import spacex.api.device.device_pb2_grpc

import time

fVerbose = True
sleepTime = 30

class DeviceStatusSeries(SeriesHelper):
    class Meta:
        series_name = "spacex.starlink.user_terminal.status"
        fields = [
            "hardware_version",
            "software_version",
            "state",
            "alert_motors_stuck",
            "alert_thermal_throttle",
            "alert_thermal_shutdown",
            "alert_unexpected_location",
            "snr",
            "seconds_to_first_nonempty_slot",
            "pop_ping_drop_rate",
            "downlink_throughput_bps",
            "uplink_throughput_bps",
            "pop_ping_latency_ms",
            "currently_obstructed",
            "fraction_obstructed"]
        tags = ["id"]

influxClient = InfluxDBClient(host="localhost", port=8086, username="script-user", password="password", database="dishstats", ssl=False, retries=1, timeout=15)

try:
    dishChannel = None
    lastId = None
    fLastFailed = False

    pending = 0
    count = 0
    while True:
        try:
            if dishChannel is None:
                dishChannel = grpc.insecure_channel("192.168.100.1:9200")
            stub = spacex.api.device.device_pb2_grpc.DeviceStub(dishChannel)
            response = stub.Handle(spacex.api.device.device_pb2.Request(get_status={}))
            status = response.dish_get_status
            DeviceStatusSeries(
                id=status.device_info.id,
                hardware_version=status.device_info.hardware_version,
                software_version=status.device_info.software_version,
                state=spacex.api.device.dish_pb2.DishState.Name(status.state),
                alert_motors_stuck=status.alerts.motors_stuck,
                alert_thermal_throttle=status.alerts.thermal_throttle,
                alert_thermal_shutdown=status.alerts.thermal_shutdown,
                alert_unexpected_location=status.alerts.unexpected_location,
                snr=status.snr,
                seconds_to_first_nonempty_slot=status.seconds_to_first_nonempty_slot,
                pop_ping_drop_rate=status.pop_ping_drop_rate,
                downlink_throughput_bps=status.downlink_throughput_bps,
                uplink_throughput_bps=status.uplink_throughput_bps,
                pop_ping_latency_ms=status.pop_ping_latency_ms,
                currently_obstructed=status.obstruction_stats.currently_obstructed,
                fraction_obstructed=status.obstruction_stats.fraction_obstructed)
            lastId = status.device_info.id
            fLastFailed = False
        except Exception as e:
            if not dishChannel is None:
                dishChannel.close()
                dishChannel = None
            if fLastFailed:
                if not lastId is None:
                    DeviceStatusSeries(id=lastId, state="DISH_UNREACHABLE")
            else:
                # Retry once, because the connection may have been lost while
                # we were sleeping
                fLastFailed = True
                continue
        pending = pending + 1
        if fVerbose:
            print("Samples: " + str(pending))
        count = count + 1
        if count > 5:
            try:
                DeviceStatusSeries.commit(influxClient)
                if fVerbose:
                    print("Wrote " + str(pending))
                pending = 0
            except Exception as e:
                print("Failed to write: " + str(e))
            count = 0
        if sleepTime > 0:
            time.sleep(sleepTime)
        else:
            break
finally:
    # Flush on error/exit
    try:
        DeviceStatusSeries.commit(influxClient)
        if fVerbose:
            print("Wrote " + str(pending))
    except Exception as e:
        print("Failed to write: " + str(e))
    influxClient.close()
    if not dishChannel is None:
        dishChannel.close()