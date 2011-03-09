import os
import io
import copy
try:
    import yaml
    filename = 'llsd.yml'
except:
    import json
    yaml = False
    filename = 'llsd.json'

llsd_info = None

def get_llsd_info():
    global llsd_info
    if llsd_info:
        return llsd_info
    b2rex_path = os.path.dirname(os.path.dirname(__file__))
    llsd_info_f = open(os.path.join(b2rex_path, filename))
    llsd_info_text = llsd_info_f.read()
    llsd_info_f.close()

    if yaml:
        llsd_info = yaml.load(llsd_info_text)
    else:
        llsd_info = json.loads(llsd_info_text)
    for sensor, sensordata in llsd_info['Sensors'].items():
        if isinstance(sensordata, str):
            llsd_info['Sensors'][sensor] = copy.deepcopy(llsd_info['Sensors'][sensordata])
    for actuator, actuatordata in llsd_info['Actuators'].items():
        if isinstance(actuatordata, str):
            llsd_info['Actuators'][actuator] = copy.deepcopy(llsd_info['Actuators'][actuatordata])
    return llsd_info

def parse_llsd_data():
    """
    Parse llsd sensor and actuator ad-hoc yaml notation.
    """
    sensors = ()
    actuators = ()
    llsd_info = get_llsd_info()
    for actuator in llsd_info['Actuators']:
        actuators += ((actuator, actuator, actuator),)
    for sensor in llsd_info['Sensors']:
        sensors += ((sensor, sensor, sensor),)
    return (sensors, actuators)

def generate_actuator_pars(actuator, actions, instdict, idx):
    """
    Generate the parameters for an actuator call from
    the actuator instance and the definition.
    """
    pars = ''
    for val in actions[actuator.type]:
        name = list(val.keys())[0]
        pardata = list(val.values())[0]
        _cls = None
        if pars:
            pars += ', '
        if pardata['type'] == 'integer':
            _cls = int
            _val = 0
        if pardata['type'] == 'float':
            _cls = float
            _val = 0
        elif pardata['type'] == 'string':
            _cls = str
            _val = ""
        if _cls:
           tmp_name = 'tmp_' + str(idx) + name
           if tmp_name in instdict:
               _val = instdict[tmp_name]
           elif hasattr(actuator, name):
               _val = _cls(getattr(actuator, name))
           elif 'default' in pardata:
               _val = pardata['default']
           pars += json.dumps(_val)
    return pars

def generate_sensor_pars(sensor, sensors):
    """
    Generate the parameters that go in a sensor
    definition.
    """
    pars = ''
    for val in sensors[sensor.type]:
        name = list(val.keys())[0]
        pardata = list(val.values())[0]
        if pars:
            pars += ', '
        pars += pardata['type'] + " " + name
    return pars

def generate_llsd(fsm, instdict):
    """
    Generate an llsd fsm script from an instance declaration.
    """
    llsd_info = get_llsd_info()
    sensors = llsd_info['Sensors']
    actions = llsd_info['Actuators']
    text = io.StringIO()

    def _write(msg):
        text.write(msg)
        text.write('\n')

    for state in fsm.states:
        _write(state.name)
        _write("{")
        for sensor in state.sensors:
            pars = generate_sensor_pars(sensor, sensors)
            _write('  '+sensor.type+'('+pars+')')
            _write("  {")
            for idx, actuator in enumerate(sensor.actuators):
                pars = generate_actuator_pars(actuator, actions, instdict, idx)
                _write("    "+actuator.type+'('+pars+')')
            _write("  }")
        _write("}")
    text.seek(0)
    return text.read()

