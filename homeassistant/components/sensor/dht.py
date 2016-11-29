"""
Support for Adafruit DHT temperature and humidity sensor.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.dht/
"""
import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    TEMP_FAHRENHEIT, CONF_NAME, CONF_MONITORED_CONDITIONS)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
from homeassistant.util.temperature import celsius_to_fahrenheit

# Update this requirement to upstream as soon as it supports Python 3.
REQUIREMENTS = ['http://github.com/adafruit/Adafruit_Python_DHT/archive/'
                '310c59b0293354d07d94375f1365f7b9b9110c7d.zip'
                '#Adafruit_DHT==1.3.0']

_LOGGER = logging.getLogger(__name__)

CONF_PIN = 'pin'
CONF_SENSOR = 'sensor'
CONF_MEDIAN = 'median'

DEFAULT_NAME = 'DHT Sensor'
DEFAULT_MEDIAN = 3

# DHT11 is able to deliver data once per second, DHT22 once every two
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=30)

SENSOR_TEMPERATURE = 'temperature'
SENSOR_HUMIDITY = 'humidity'
SENSOR_TYPES = {
    SENSOR_TEMPERATURE: ['Temperature', None],
    SENSOR_HUMIDITY: ['Humidity', '%']
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SENSOR): cv.string,
    vol.Required(CONF_PIN): cv.string,
    vol.Optional(CONF_MEDIAN, default=DEFAULT_MEDIAN): cv.positive_int,
    vol.Optional(CONF_MONITORED_CONDITIONS, default=[]):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the DHT sensor."""
    # pylint: disable=import-error
    import Adafruit_DHT

    SENSOR_TYPES[SENSOR_TEMPERATURE][1] = hass.config.units.temperature_unit
    available_sensors = {
        "DHT11": Adafruit_DHT.DHT11,
        "DHT22": Adafruit_DHT.DHT22,
        "AM2302": Adafruit_DHT.AM2302
    }
    sensor = available_sensors.get(config.get(CONF_SENSOR))
    pin = config.get(CONF_PIN)
    median = config.get(CONF_MEDIAN)

    if not sensor:
        _LOGGER.error("DHT sensor type is not supported")
        return False

    data = DHTClient(Adafruit_DHT, sensor, pin)
    dev = []
    name = config.get(CONF_NAME)

    try:
        for variable in config[CONF_MONITORED_CONDITIONS]:
            dev.append(DHTSensor(
                data, variable, SENSOR_TYPES[variable][1], name, median))
    except KeyError:
        pass

    add_devices(dev)


class DHTSensor(Entity):
    """Implementation of the DHT sensor."""

    def __init__(self, dht_client, sensor_type, temp_unit, name, median):
        """Initialize the sensor."""
        self.client_name = name
        self._name = SENSOR_TYPES[sensor_type][0]
        self.dht_client = dht_client
        self.temp_unit = temp_unit
        self.type = sensor_type
        self.data = []
        self._state = None
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        # Median is used to filter out outliers. median of 3 will filter
        # single outliers, while  median of 5 will filter double outliers
        # Use median_count = 1 if no filtering is required.
        self.median_count = median
        self.update()

    @property
    def name(self):
        """Return the name of the sensor."""
        return '{} {}'.format(self.client_name, self._name)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    def update(self):
        """
        Get the latest data from the DHT and updates the states.
        This uses a rolling median over 3 values to filter out outliers.
        """
        try:
            _LOGGER.debug("Polling data for %s", self.name)
            self.dht_client.update()
            data = self.dht_client.data
        except IOError as ioerr:
            _LOGGER.info("Polling error %s", ioerr)
            data = None
            return

        if data is not None:
            _LOGGER.debug("%s = %s", self.name, data)
            if self.type == SENSOR_TEMPERATURE:
                temperature = round(data[SENSOR_TEMPERATURE], 1)
                    if (temperature >= -20) and (temperature < 80):
                        # self._state = temperature
                        self.data.append(temperature)
                        if self.temp_unit == TEMP_FAHRENHEIT:
                            # self._state = round(celsius_to_fahrenheit(temperature), 1)
                            self.data.append(round(celsius_to_fahrenheit(temperature), 1))
            elif self.type == SENSOR_HUMIDITY:
                humidity = round(data[SENSOR_HUMIDITY], 1)
                if (humidity >= 0) and (humidity <= 100):
                    # self._state = humidity
                    self.data.append(humidity)
        else:
            _LOGGER.info("Did not receive any data from DHT sensor %s",
                         self.name)
            # Remove old data from median list or set sensor value to None
            # if no data is available anymore
            if len(self.data) > 0:
                self.data = self.data[1:]
            else:
                self._state = None
            return
        
        _LOGGER.debug("Data collected: %s", self.data)
        if len(self.data) > self.median_count:
            self.data = self.data[1:]

        if len(self.data) == self.median_count:
            median = sorted(self.data)[int((self.median_count - 1) / 2)]
            _LOGGER.debug("Median is: %s", median)
            self._state = median
        else:
            _LOGGER.debug("Not yet enough data for median calculation")


class DHTClient(object):
    """Get the latest data from the DHT sensor."""

    def __init__(self, adafruit_dht, sensor, pin):
        """Initialize the sensor."""
        self.adafruit_dht = adafruit_dht
        self.sensor = sensor
        self.pin = pin
        self.data = dict()

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Get the latest data the DHT sensor."""
        humidity, temperature = self.adafruit_dht.read_retry(self.sensor,
                                                             self.pin)
        if temperature:
            self.data[SENSOR_TEMPERATURE] = temperature
        if humidity:
            self.data[SENSOR_HUMIDITY] = humidity
