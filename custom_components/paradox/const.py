"""Constants for the Paradox integration."""
DOMAIN = 'paradox'
MANUFACTURER = 'Paradox, Inc'

# Configuration
CONF_MODEL = 'type'
CONF_USERCODE = 'usercode'
CONF_MODULE = 'module'

# Defaults
DEFAULT_PORT = 80
DEFAULT_PASSWORD = 'paradox'
DEFAULT_USERNAME = 'master'
DEFAULT_USERCODE = '1234'
DEFAULT_TIMEOUT = 10
DEFAULT_SCAN_INTERVAL = 30

# Alarm Panel
CONF_ALARM_CONTROL_PANEL = 'alarm_control_panel'

# Camera
CONF_CAMERA = 'camera'
CONF_CAMERA_PROFILE = 'channel_type'
CAMERA_PROFILES = ['Low', 'Normal', 'High']
DEFAULT_CAMERA_PROFILE = 'Normal'
CAMERA_BANDWIDTH = {
    'Low': 128000,
    'Normal': 256000,
    'High': 512000
}
DEFAULT_FFMPEG_ARGUMENTS = '-pred 1'
