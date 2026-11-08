"""Build-time device differences. Nothing here reads or changes a router."""
import html
import json
from pathlib import Path, PurePosixPath
import re
import shlex

ROOT = Path(__file__).resolve().parent.parent
DEVICES = ROOT / 'build/devices'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative_file(value):
    require(isinstance(value, str) and bool(value), 'Expected a repository-relative path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and str(path) == value,
            'Expected a normalized repository-relative path: ' + value)
    return value


def validate_device(device):
    require(device['schema'] == 1, 'Unsupported device schema')
    require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', device['id']), 'Invalid device id')
    require(re.fullmatch(r'[A-Z0-9][A-Z0-9_-]*', device['model']), 'Invalid model')
    require(device['adapter'] == 'asus-hnd-arm32', 'Unsupported adapter; port its ABI first')
    abi = device['abi']
    require((abi['elf_machine'], abi['bits'], abi['little_endian'], abi['nvram_tuple_bytes']) ==
            ('EM_ARM', 32, True, 20), 'Adapter requires the ASUS ARM32 little-endian ABI')
    require(re.fullmatch(r'arm-linux-gnueabi\.\d+\.\d+', abi['zig_target']), 'Invalid ARM compiler target')
    require(re.fullmatch(r'[a-zA-Z0-9_]+', abi['cpu']), 'Invalid CPU')
    base = device['base']
    for key in ['vendor_image', 'contracts']:
        relative_file(base[key])
    require(set(device['sources']) == {'softcenter', 'fancyss', 'merlin'}, 'Missing/unknown source manifests')
    for value in device['sources'].values():
        relative_file(value)
    require(re.fullmatch(r'[A-Za-z0-9_.-]+', base['image_prefix']), 'Invalid image prefix')
    for key in ['version', 'display_version']:
        require(isinstance(base[key], str) and base[key] and not any(c in base[key] for c in '\r\n@'),
                'Invalid base version')
    geometry = device['image']
    require(geometry['format'] == 'asus-pure-ubi', 'Unsupported image format')
    for key, value in geometry.items():
        if key not in ['format', 'rootfs_volume_name', 'compression']:
            require(type(value) is int and value >= 0, 'Invalid image integer: ' + key)
    peb, minimum, vid, data = (geometry[k] for k in ['peb_size', 'min_io_size', 'vid_offset', 'data_offset'])
    require(minimum >= 512 and minimum & (minimum - 1) == 0, 'Invalid minimum I/O size')
    require(peb > data >= vid + 64 and vid >= 64 and peb % minimum == 0 and
            vid % minimum == 0 and data % minimum == 0, 'Invalid UBI geometry')
    require(data + 128*172 <= peb, 'UBI volume table does not fit erase block')
    require(geometry['rootfs_offset'] >= 2 * peb and geometry['rootfs_offset'] % peb == 0,
            'Invalid rootfs offset')
    require(geometry['trailer_size'] == 20 and geometry['descriptor_size'] >= 24 and
            geometry['model_size'] > 0 and geometry['model_offset'] + geometry['model_size'] <= geometry['descriptor_size'],
            'Unsupported ASUS footer layout')
    require(len(device['model'].encode('ascii')) < geometry['model_size'], 'Model does not fit descriptor')
    require(geometry['ubifs_format'] == 4, 'Only UBIFS format 4 is supported')
    require(0 < geometry['min_rootfs_lebs'] < geometry['max_lebs'] and
            geometry['rootfs_volume_id'] < 128 and geometry['boot_volume_id'] < 128 and
            geometry['rootfs_volume_id'] != geometry['boot_volume_id'] and geometry['layout_volume_id'] >= 128 and
            geometry['min_image_bytes'] < geometry['max_image_bytes'], 'Invalid image bounds')
    require(re.fullmatch(r'[a-zA-Z0-9_]+', geometry['rootfs_volume_name']) and
            len(geometry['rootfs_volume_name']) <= 127, 'Invalid rootfs volume name')
    require(geometry['compression'] in ['zlib', 'lzo', 'none'], 'Unsupported UBIFS compression')
    require(geometry['fanout'] >= 3 and geometry['log_lebs'] >= 2 and
            geometry['orphan_lebs'] > 0 and geometry['journal_bytes'] > 0, 'Invalid UBIFS options')
    plugins = device['plugins']
    for key in ['legacy_marker', 'extended_marker', 'extended_productid']:
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', plugins[key]), 'Invalid plugin token: ' + key)
    require(plugins['extended_productid'] == device['model'], 'Plugin productid must match device')
    require(re.fullmatch(r'/[A-Za-z0-9_./-]+', plugins['extended_loader']) and
            '..' not in PurePosixPath(plugins['extended_loader']).parts, 'Invalid plugin loader')
    require(re.fullmatch(r'[A-Za-z0-9 ]+', plugins['display_platform']), 'Invalid plugin display platform')
    return device


def load_device(device_id, directory=DEVICES):
    require(isinstance(device_id, str) and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', device_id),
            'Invalid device id')
    path = Path(directory) / (device_id + '.json')
    require(path.is_file() and not path.is_symlink(), 'Unknown device: ' + device_id)
    device = validate_device(json.loads(path.read_text()))
    require(device['id'] == device_id, 'Device filename/id mismatch')
    return device


DEVICE_ID = json.loads((ROOT / 'build/release_config.json').read_text())['device']
DEVICE = load_device(DEVICE_ID)
DEVICE_INPUTS = ['build/device_config.py', 'build/devices/' + DEVICE_ID + '.json', 'build/release_config.json']


def compiler_flags(device=DEVICE, cpu=True):
    result = ['-target', device['abi']['zig_target']]
    if cpu:
        result.append('-mcpu=' + device['abi']['cpu'])
    return result


def fixture_model_flag(device=DEVICE):
    return '-DLOCALMOD_DEVICE_MODEL="' + device['model'] + '"'


def leb_size(device=DEVICE):
    return device['image']['peb_size'] - device['image']['data_offset']


def model_from_image(raw, device=DEVICE):
    geometry = device['image']
    end = len(raw) - geometry['trailer_size']
    start = end - geometry['descriptor_size'] + geometry['model_offset']
    require(start >= 0 and start + geometry['model_size'] <= end, 'Missing ASUS model footer')
    return raw[start:start + geometry['model_size']].split(b'\0', 1)[0].decode('ascii')


def require_model(raw, device=DEVICE):
    require(model_from_image(raw, device) == device['model'], 'Firmware model does not match ' + device['model'])


def mkfs_flags(device=DEVICE):
    g = device['image']
    return ['-U', '-m', str(g['min_io_size']), '-e', str(leb_size(device)), '-c', str(g['max_lebs']),
            '-x', g['compression'], '-f', str(g['fanout']), '-l', str(g['log_lebs']),
            '-p', str(g['orphan_lebs']), '-F', '-j', str(g['journal_bytes'])]


def render_build_job(text, device=DEVICE):
    require(text.count('@UBIFS_ARGS@') == 1, 'Missing/duplicate UBIFS build placeholder')
    return text.replace('@UBIFS_ARGS@', shlex.join(mkfs_flags(device)))


def render_source(path, config=None, device=DEVICE):
    """Resolve owned templates before staging; the router needs no new parser."""
    text = (ROOT / path).read_text()
    tokens = {
        '@MODEL@': device['model'], '@BASE_DISPLAY@': device['base']['display_version'],
        '@PLUGIN_LEGACY@': device['plugins']['legacy_marker'],
        '@PLUGIN_EXTENDED@': device['plugins']['extended_marker'],
        '@PLUGIN_MODEL@': device['plugins']['extended_productid'],
        '@PLUGIN_LOADER@': device['plugins']['extended_loader'],
        '@PLUGIN_PLATFORM@': device['plugins']['display_platform'],
    }
    if config is not None:
        tokens.update({'@REVISION@': config['variant'] + '-' + config['revision'],
                       '@SOFTCENTER_VERSION@': config['software_center_version']})
    for key, value in tokens.items():
        text = text.replace(key, html.escape(value, quote=True) if str(path).endswith('.asp') else value)
    require(not re.search(r'@(MODEL|BASE_DISPLAY|PLUGIN_[A-Z_]+|REVISION|SOFTCENTER_VERSION)@', text),
            'Unresolved device/release placeholder: ' + str(path))
    return text
