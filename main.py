import exiftool
from typing import List, Dict
import csv
import os
import sys
import subprocess
import re
import datetime
import pandas as pd

PATH_CSV_CAM = 'cam.csv'
PATH_CSV_INV_CAM = 'inv_cameras.csv'
PATH_CSV_LENS = 'lens.csv'
PATH_CSV_INV_LENS = 'inv_lens.csv'

FIGURE = 'fig.pdf'

TAG_MIME = 'File:MIMEType'
TAG_CAM_MAKE = 'EXIF:Make'
TAG_CAM_MODEL = 'EXIF:Model'
TAG_PIC_EXPOSURE = 'EXIF:ExposureTime'
TAG_PIC_APERTURE = 'EXIF:FNumber'
TAG_PIC_ISO = 'EXIF:ISO'
TAG_LENS_INFO = 'EXIF:LensInfo'
TAG_LENS_MODEL = 'EXIF:LensModel'
TAG_PIC_FOCAL = 'EXIF:FocalLength'
TAG_PIC_FOCAL35 = 'EXIF:FocalLengthIn35mmFormat'
TAG_PIC_DATE_TIME_ORIGINAL = 'EXIF:DateTimeOriginal'
TAG_PIC_PHOTOGRAPHER = 'EXIF:Photographer'
TAG_PIC_SOFTWARE = 'EXIF:Software'

# UTILS

def float_compare(fl1: float, fl2: float) -> bool:
    return abs(fl2 - fl1) < 0.000001

def ask(question: str) -> str:
    print(f'\n{question}\n')
    return input()

def float_or_zero(text: str) -> float:
    try:
        return float(text)
    except:
        return 0.0

def int_or_zero(text: str) -> int:
    try:
        return int(text)
    except:
        return 0

def datetime_or_min(text: str) -> datetime.datetime:
    date_split = text.split(' ')
    if len(date_split) >= 2:
        date_date = date_split[0].split(':')
        date_time = date_split[1].split(':')
        if len(date_date) == 3 and len(date_time) == 3:
            try:
                return datetime.datetime(int_or_zero(date_date[0]), int_or_zero(date_date[1]), int_or_zero(date_date[2]), int_or_zero(date_time[0]), int_or_zero(date_time[1]), int_or_zero(date_time[2]))
            except:
                return datetime.datetime.min
    return datetime.datetime.min

def open_file(path: str):
    # https://stackoverflow.com/questions/35304492/python-open-multiple-images-in-default-image-viewer
    imageViewerFromCommandLine = {'linux':'xdg-open',
                                'win32':'explorer',
                                'darwin':'open'}[sys.platform]
    subprocess.run([imageViewerFromCommandLine, path])

def exif_set_tags(path: str, changes: Dict[str,str], exif: exiftool.ExifToolHelper):
    exif.set_tags(path, changes, "-overwrite_original")

def ask_directory(question: str) -> str:
    dir = ask(question)
    dirs = dir.split('|')
    for dir_s in dirs:
        if not os.path.exists(dir_s):
            print('Directory does not exist')
            return ''
    return dir

def range_graph_float(start: float, stop: float, interval: float) -> List[float]:
    ret: List[float] = [start]
    next = start
    while next < stop:
        next += interval
        ret.append(next)
    return ret

def range_graph_int(start: int, stop: int, interval: int) -> List[int]:
    ret: List[int] = [start]
    next = start
    while next < stop:
        next += interval
        ret.append(next)
    return ret

# DATA

PicDiff = Dict[str,tuple[str,str]]

class CameraData:
    def __init__(self, make: str, model: str, crop: float, shortcut: bool, lens_optional: bool, film: bool):
        self.make = make
        self.model = model
        self.has_shortcut = shortcut
        self.crop = crop
        self.lens_optional = lens_optional
        self.film = film

    def is_valid(self) -> bool:
        return self.model != '' and self.crop > 0.0

    def name(self) -> str:
        if not self.is_valid:
            return '(NO CAM SET)' 
        return self.model if self.make == '' else f'{self.make} {self.model}'
    
    def equals(self, other: CameraData) -> PicDiff:
        diffs: PicDiff = dict()
        if self.make != other.make:
            diffs[TAG_CAM_MAKE] = (self.make, other.make)
        if self.model != other.model:
            diffs[TAG_CAM_MODEL] = (self.model, other.model)
        return diffs

class LensData:
    def __init__(self, model: str, focal_min: float, focal_max: float, aperture_min: float, aperture_max: float, shortcut: bool):
        self.model = model
        self.focal_min = focal_min
        self.focal_max = focal_max
        self.aperture_min = aperture_min
        self.aperture_max = aperture_max
        self.has_shortcut = shortcut

    def is_valid(self) -> bool:
        return self.model != '' and self.focal_min != 0 and self.aperture_min != 0
    
    def name(self) -> str:
        if not self.is_valid():
            return '(NO LENS SET)'
        text = f'{self.model} ({self.focal_min}'
        text += 'mm' if self.focal_max == 0 else f'-{self.focal_max}mm'
        text += f' f/{self.aperture_min}'
        text += '' if self.aperture_max == 0 else f'-{self.focal_max}'
        text += ')'
        return text
    
    def create_lens_info(self, fix: bool) -> str:
        focal_max = self.focal_max if self.focal_max > 0.0 or not fix else self.focal_min
        aperture_max = self.aperture_max if self.aperture_max > 0.0 or not fix else self.aperture_min
        return f'{self.focal_min} {focal_max} {self.aperture_min} {aperture_max}'
    
    def equals(self, other: LensData) -> List[str]:
        diffs: PicDiff = dict()
        if self.model != other.model:
            diffs[TAG_LENS_MODEL] = (self.model, other.model)
        if (not float_compare(self.focal_min, other.focal_min) or not float_compare(self.aperture_min, other.aperture_min)
            or not float_compare(self.focal_max, other.focal_max) or not (self.aperture_max, other.aperture_max)):
            diffs[TAG_LENS_INFO] = (self.create_lens_info(False), other.create_lens_info(False))
        return diffs
    
class ScannedLensData:
    def __init__(self, model: str, lens: LensData):
        self.model = model
        self.focal_min: List[float] = [lens.focal_min] if lens.focal_min != 0.0 else []
        self.focal_max: List[float] = [lens.focal_max] if lens.focal_max != 0.0 else []
        self.aperture_min: List[float] = [lens.aperture_min] if lens.aperture_min != 0.0 else []
        self.aperture_max: List[float] = [lens.aperture_max] if lens.aperture_max != 0.0 else []
    
    def add(self, lens: LensData):
        if lens.focal_min != 0.0 and lens.focal_min not in self.focal_min:
            self.focal_min.append(lens.focal_min)
        if lens.focal_max != 0.0 and lens.focal_max not in self.focal_max:
            self.focal_max.append(lens.focal_max)
        if lens.aperture_min != 0.0 and lens.aperture_min not in self.aperture_min:
            self.aperture_min.append(lens.aperture_min)
        if lens.aperture_max != 0.0 and lens.aperture_max not in self.aperture_max:
            self.aperture_max.append(lens.aperture_max)

    def is_valid(self) -> bool:
        return self.model != '' and len(self.focal_min) != 0 and len(self.aperture_min) != 0
    
class CsvData:
    def __init__(self, cams: List[CameraData], lenses: List[LensData], inv_cams: List[str], inv_lenses: List[str]):
        self.cameras = cams
        self.lenses = lenses
        self.invalid_cameras = inv_cams
        self.invalid_lenses = inv_lenses
        self.lookup_model_to_lens: Dict[str, LensData] = dict()
        self.lookup_name_to_camera: Dict[str, CameraData] = dict()
        self.lookup_shortcut_lens: List[LensData] = []
        self.lookup_shortcut_camera: List[CameraData] = []
        self.reload_lookups()

    def reload_lookups(self):
        self.lookup_model_to_lens = dict()
        self.lookup_shortcut_lens = []
        for lens in self.lenses:
            if lens.model != '':
                self.lookup_model_to_lens[lens.model] = lens
            if lens.has_shortcut:
                self.lookup_shortcut_lens.append(lens)

        self.lookup_name_to_camera = dict()
        self.lookup_shortcut_camera = []
        for camera in self.cameras:
            if camera.model != '':
                self.lookup_name_to_camera[camera.name()] = camera
            if camera.has_shortcut:
                self.lookup_shortcut_camera.append(camera)

class PictureData:
    def __init__(self, path: str, focal_length: float, focal_length_in_35mm_format: int, iso: int, exposure_time: float, aperture: float, created: datetime.datetime, photographer: str, cam: CameraData, lens: LensData):
        self.path = path
        self.focal_length = focal_length
        self.focal_length_in_35mm_format = focal_length_in_35mm_format
        self.iso = iso
        self.exposure_time = exposure_time
        self.aperture = aperture
        self.camera = cam
        self.lens = lens
        self.created = created
        self.photographer = photographer

    def name(self) -> str:
        txt_focal = '?' if self.focal_length == 0 else self.focal_length
        txt_focal35 = '?' if self.focal_length_in_35mm_format == 0 else self.focal_length_in_35mm_format
        txt_iso = '?' if self.iso == 0 else self.iso
        txt_exposure = '?' if self.exposure_time else self.exposure_time
        txt_aperture = '?' if self.aperture else self.aperture
        return f'{txt_focal}({txt_focal35})mm {txt_iso} ISO @ {txt_exposure}s f/{txt_aperture}'
    
    def equals(self, other: PictureData) -> PicDiff:
        diffs: PicDiff = dict()

        diffs_part = self.camera.equals(other.camera)
        for diff_part in diffs_part:
            diffs[diff_part] = diffs_part[diff_part]
        diffs_part = self.lens.equals(other.lens)
        for diff_part in diffs_part:
            diffs[diff_part] = diffs_part[diff_part]
            
        if not float_compare(self.focal_length, other.focal_length):
            diffs[TAG_PIC_FOCAL] = (str(self.focal_length), str(other.focal_length))
        if self.focal_length_in_35mm_format != other.focal_length_in_35mm_format:
            diffs[TAG_PIC_FOCAL35] = (str(self.focal_length_in_35mm_format), other.focal_length_in_35mm_format)
        if self.iso != other.iso:
            diffs[TAG_PIC_ISO] = (str(self.iso), str(other.iso))
        if not float_compare(self.exposure_time, other.exposure_time):
            diffs[TAG_PIC_EXPOSURE] = (str(self.exposure_time), str(other.exposure_time))
        if not float_compare(self.aperture, other.aperture):
            diffs[TAG_PIC_APERTURE] = (str(self.aperture), str(other.aperture))
        if self.photographer != other.photographer:
            diffs[TAG_PIC_PHOTOGRAPHER] = (self.photographer, other.photographer)
        return diffs

NodePics = Dict[str,PictureData]
NodeGroups = Dict[str,NodePics]
NodeDirs = Dict[str,NodeGroups]

# DATA UTILS

def get_preferred_picture_data(node_pics: NodePics) -> PictureData:
    for k in node_pics:
        if k.lower() in ['.jpeg', '.jpg']:
            return node_pics[k]
    for k in node_pics:
        if k.lower() in ['.png', '.bmp']:
            return node_pics[k]
    return next(iter(node_pics.values()))

# LOADING / WRITING DATA

def load_csv_data() -> CsvData:
    saved_cameras: List[CameraData] = []
    if os.path.exists(PATH_CSV_CAM):
        with open(PATH_CSV_CAM, 'r') as csv_d:
            reader = csv.reader(csv_d)
            for row in reader:
                saved_cameras.append(CameraData(row[0], row[1], float(row[2]), row[3] == "1", row[4] == "1", row[5] == "1"))
    
    saved_lenses: List[LensData] = []
    if os.path.exists(PATH_CSV_LENS):
        with open(PATH_CSV_LENS, 'r') as csv_d:
            reader = csv.reader(csv_d)
            for row in reader:
                saved_lenses.append(LensData(row[0], float(row[1]), float(row[2]), float(row[3]), float(row[4]), row[5] == "1"))

    saved_inv_cameras: List[str] = []
    if os.path.exists(PATH_CSV_INV_CAM):
        with open(PATH_CSV_INV_CAM, 'r') as csv_d:
            reader = csv.reader(csv_d)
            for row in reader:
                saved_inv_cameras.append(row[0])

    saved_inv_lenses: List[str] = []
    if os.path.exists(PATH_CSV_INV_LENS):
        with open(PATH_CSV_INV_LENS, 'r') as csv_d:
            reader = csv.reader(csv_d)
            for row in reader:
                saved_inv_lenses.append(row[0])

    return CsvData(saved_cameras, saved_lenses, saved_inv_cameras, saved_inv_lenses)

def write_csv_data(csv_data: CsvData):
    with open(PATH_CSV_CAM, 'w+') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows([[x.make, x.model, str(x.crop), "1" if x.has_shortcut else "0", "1" if x.lens_optional else "0", "1" if x.film else "0"] for x in csv_data.cameras])
    
    with open(PATH_CSV_LENS, 'w+') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows([[x.model, x.focal_min, x.focal_max, x.aperture_min, x.aperture_max, "1" if x.has_shortcut else "0"] for x in csv_data.lenses])

    with open(PATH_CSV_INV_CAM, 'w+') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows([[x] for x in csv_data.invalid_cameras])

    with open(PATH_CSV_INV_LENS, 'w+') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows([[x] for x in csv_data.invalid_lenses])

def scan_dir_recursive(directory_search: str, dir_files: Dict[str,List[str]]):
    files: List[str] = []
    dirs: List[str] = []

    print(f'Scanning "{directory_search}"...')
    for entry in os.scandir(directory_search):
        if entry.is_dir(follow_symlinks=False):
            dirs.append(entry.path)
        else:
            if os.stat(entry.path).st_size > 250:
                files.append(entry.path)
    print(f'Found {len(files)} files and {len(dirs)} directories in "{directory_search}"')

    if len(files) > 0:
        dir_files[directory_search] = files
    
    for dir in dirs:
        scan_dir_recursive(dir, dir_files)

def perform_scan(directory: str, exif: exiftool.ExifToolHelper) -> Dict[str,List[dict]]:
    dir_files: Dict[str, List[str]] = dict()
    for dir in directory.split('|'):
        scan_dir_recursive(dir, dir_files)
    
    dir_files_processed: Dict[str, List[dict]] = dict()
    tags = [
        TAG_MIME,
        TAG_CAM_MAKE,
        TAG_CAM_MODEL,
        TAG_PIC_EXPOSURE,
        TAG_PIC_APERTURE,
        TAG_PIC_ISO,
        TAG_LENS_INFO,
        TAG_LENS_MODEL,
        TAG_PIC_FOCAL,
        TAG_PIC_FOCAL35,
        TAG_PIC_DATE_TIME_ORIGINAL,
        TAG_PIC_PHOTOGRAPHER
    ]

    for (i_dir,(dir,files)) in enumerate(dir_files.items()):
        print(f'Processing {len(files)} files from "{dir}" ({(i_dir + 1)}/{len(dir_files)})')
        failed_items: List[str] = []

        files_tags: List = []
        idx_pointer = 0
        while(idx_pointer < len(files)):
            idx_start = idx_pointer
            idx_pointer = min(idx_start + 50, len(files))
            files_slice = files[idx_start:idx_pointer]

            try:
                print(f'Processing batch of {len(files_slice)} files {idx_start + 1}-{idx_pointer}/{len(files)} from "{dir}" ({(i_dir + 1)}/{len(dir_files)})')
                files_tags.extend(exif.get_tags(files_slice, tags))
            except:
                print(f'Error while processing batch, processing files one by one instead')
                for (split_idx, split_file) in enumerate(files_slice):
                    if split_idx % 10 == 9:
                        print(f'Processing broken batch file {split_idx+1}/{len(files_slice)} from "{dir}" ({(i_dir + 1)}/{len(dir_files)})')
                    try:
                        files_tags.extend(exif.get_tags(split_file, tags))
                    except:
                        print(f'Could not read file "{split_file}"')
                        failed_items.append(split_file)

        if len(files_tags) == 0:
            continue

        files_dict: List[dict] = []
        for file_tags in files_tags:
            if type(file_tags) is not dict:
                print(f'Skipped file "{file_tags}", unable to get dict')
                failed_items.append(file_tags)
                continue
            mime = file_tags.get(TAG_MIME)
            if type(mime) is not str or not mime.lower().startswith("image"):
                print(f'Skipped file "{file_tags}", not correct mime type')
                continue
            files_dict.append(file_tags)
            
        msg = f'Collected metadata for {len(files_dict)}/{len(files)} files in "{dir}"'
        if len(failed_items) > 0:
            msg += f' => {len(failed_items)} failed ({failed_items})'
        print(msg)
        dir_files_processed[dir] = files_dict

    return dir_files_processed

def convert_scanned_data(dataDict: dict) -> PictureData:
    path = dataDict['SourceFile']

    cam_make = dataDict[TAG_CAM_MAKE] if TAG_CAM_MAKE in dataDict else ''
    cam_model = dataDict[TAG_CAM_MODEL] if TAG_CAM_MODEL in dataDict else ''
    cam = CameraData(cam_make, cam_model, 1.0, False, False, False)

    lens_model = dataDict[TAG_LENS_MODEL] if TAG_LENS_MODEL in dataDict else ''
    lens_info_raw = dataDict[TAG_LENS_INFO] if TAG_LENS_INFO in dataDict else ''
    lens_info_split = lens_info_raw.split(' ') if len(lens_info_raw) > 0 else []
    lens_info_focal_min = float_or_zero(lens_info_split[0]) if len(lens_info_split) > 0 else 0.0
    lens_info_focal_max = float_or_zero(lens_info_split[1]) if len(lens_info_split) > 1 else 0.0
    lens_info_aperture_min = float_or_zero(lens_info_split[2]) if len(lens_info_split) > 2 else 0.0
    lens_info_aperture_max = float_or_zero(lens_info_split[3]) if len(lens_info_split) > 3 else 0.0
    lens = LensData(lens_model, lens_info_focal_min, lens_info_focal_max, lens_info_aperture_min, lens_info_aperture_max, False)

    pic_iso = int_or_zero(dataDict[TAG_PIC_ISO]) if TAG_PIC_ISO in dataDict else 0
    pic_focal35 = int_or_zero(dataDict[TAG_PIC_FOCAL35]) if TAG_PIC_FOCAL35 in dataDict else 0
    pic_aperture = float_or_zero(dataDict[TAG_PIC_APERTURE]) if TAG_PIC_APERTURE in dataDict else 0.0
    pic_focal = float_or_zero(dataDict[TAG_PIC_FOCAL]) if TAG_PIC_FOCAL in dataDict else 0.0
    pic_exposure = float_or_zero(dataDict[TAG_PIC_EXPOSURE]) if TAG_PIC_EXPOSURE in dataDict else 0.0
    pic_date = datetime_or_min(dataDict[TAG_PIC_DATE_TIME_ORIGINAL] if TAG_PIC_DATE_TIME_ORIGINAL in dataDict else '')
    pic_photographer = dataDict[TAG_PIC_PHOTOGRAPHER] if TAG_PIC_PHOTOGRAPHER in dataDict else ''

    return PictureData(path, pic_focal, pic_focal35, pic_iso, pic_exposure, pic_aperture, pic_date, pic_photographer, cam, lens)

regex_pixel_file_extractor = re.compile('^PXL_[0-9]+_[0-9]+')
def fix_naming_system_irregularities(pic: PictureData, name: str) -> str:
    if pic.camera.make.lower() == 'google' and pic.camera.model.lower().find('pixel') != -1:
        result = regex_pixel_file_extractor.search(name)
        if result is not None:
            return result.group(0)
    return name

def convert_all_scanned_data(dir_files: Dict[str,List[dict]]) -> NodeDirs:
    node_dirs: NodeDirs = dict()
    for (raw_dir, raw_files) in dir_files.items():
        node_dirs[raw_dir] = dict()
        print(f'Converting data from {len(raw_files)} files in "{raw_dir}"')
        for raw_file in raw_files:
            conv_file = convert_scanned_data(raw_file)
            (name, ext) = os.path.splitext(os.path.basename(conv_file.path))
            name = fix_naming_system_irregularities(conv_file, name)
            base = name if name != "" else conv_file.path
            if base not in node_dirs[raw_dir]:
                node_dirs[raw_dir][base] = dict()
            node_dirs[raw_dir][base][ext.lower()] = conv_file
        print(f'Converted data to {len(node_dirs[raw_dir])} file groups in "{raw_dir}"')
    return node_dirs

def perform_scan_and_convert(dir: str, exif: exiftool.ExifToolHelper) -> NodeDirs:
    dir_files = perform_scan(dir, exif)
    return convert_all_scanned_data(dir_files)

# DATA COLLECTION

def collect_gear_data(node_dirs: NodeDirs) -> tuple[List[ScannedLensData], List[CameraData]]:
    found_lenses: Dict[str,ScannedLensData] = dict()
    found_cams: Dict[str,CameraData] = dict()
    for (_, node_groups) in node_dirs.items():
        for (_, node_pics) in node_groups.items():
            for (_, pic) in node_pics.items():
                if pic.lens.model != '':
                    if pic.lens.model not in found_lenses:
                        found_lenses[pic.lens.model] = ScannedLensData(pic.lens.model, pic.lens)
                    else:
                        found_lenses[pic.lens.model].add(pic.lens)
                if pic.camera.model != '':
                    cam_name = pic.camera.name()
                    if cam_name not in found_cams:
                        found_cams[cam_name] = pic.camera
    return_lenses: List[ScannedLensData] = [found_lenses[x] for x in found_lenses.keys()]
    return_cams: List[CameraData] = [found_cams[x] for x in found_cams.keys()]
    return (return_lenses, return_cams)

def ask_for_lens_value_if_needed(model: str, name: str, values: List[float], take_over_name: str, take_over_value: float) -> float:
    # Asking for take over if no values available
    if len(values) == 0:
        if take_over_name != '' and take_over_value != 0.0:
            take_over = ask(f'Lens model "{model}" does not have a value for {name} but the value {take_over_value} for {take_over_name}, type "1" to copy it')
            if take_over == '1':
                return take_over_value
            
    if len(values) > 0:
        print(f'Lens model "{model}" has the following values for {name}: {values}')
        selected = int_or_zero(ask('Which index would you like to pick (starting at 1, invalid = none)'))
        if selected > 0 and selected <= len(values):
            return values[selected - 1]
    
    return float_or_zero(ask(f'Please provide a new value for {name} for lens model "{model}"'))

def complete_camera_data(existing_data: CameraData) -> CameraData | None:
    cam_name = existing_data.name()
    crop = float_or_zero(ask(f'Please specify a crop factor for camera "{cam_name}"')) if existing_data.crop <= 0.0 else existing_data.crop
    if crop <= 0.0:
        print('Crop is not valid')
        return None
    shortcut = ask(f'Type "1" to add a shortcut for camera "{cam_name}"') == "1"
    lens_optional = ask(f'Type "1" to make lenses optional for camera "{cam_name}"') == "1"
    film = ask(f'Type "1" to make camera "{cam_name}" use film') == "1"

    new_cam = CameraData(existing_data.make, existing_data.model, crop, shortcut, lens_optional, film)
    if not new_cam.is_valid():
        print(f'Camera "{cam_name}" has invalid values')
        return None
    return new_cam

def complete_lens_data(existing_data: ScannedLensData) -> LensData | None:
    val_focal_min = ask_for_lens_value_if_needed(existing_data.model, "shortest focal length", existing_data.focal_min, '', 0.0)
    val_focal_max = ask_for_lens_value_if_needed(existing_data.model, "longest focal length", existing_data.focal_max, 'shortest focal length', val_focal_min)
    val_aperture_min = ask_for_lens_value_if_needed(existing_data.model, "widest aperture", existing_data.aperture_min, '', 0.0)
    val_aperture_max = ask_for_lens_value_if_needed(existing_data.model, "widest aperture on max focal", existing_data.aperture_max, 'widest aperture', val_aperture_min)
    shortcut = ask(f'Type "1" to add a shortcut for lens model "{existing_data.model}"') == "1"

    new_lens = LensData(existing_data.model, val_focal_min, val_focal_max, val_aperture_min, val_aperture_max, shortcut)
    if not new_lens.is_valid():
        print(f'Lens model "{new_lens.model}" has invalid values')
        return None
    return new_lens

def scan_for_gear(node_dirs: NodeDirs, csv_data: CsvData):
    (col_lens, col_cam) = collect_gear_data(node_dirs)
    show_mismatches = ask(f'Collected {len(col_cam)} cameras and {len(col_lens)} lenses\nType "1" to also show mismatches') == '1'

    for lens in col_lens:
        if lens.model in csv_data.invalid_lenses:
            print(f'Skipping lens model "{lens.model}" as it is in list of invalid lenses')
            continue
        
        if lens.model in csv_data.lookup_model_to_lens:
            if not show_mismatches:
                print(f'Skipping lens model "{lens.model}" as a match is in list')
                continue
            else:
                match_lens = csv_data.lookup_model_to_lens[lens.model]
                if match_lens.focal_min != 0.0 and match_lens.focal_min not in lens.focal_min:
                    lens.focal_min.append(match_lens.focal_min)
                if match_lens.focal_max != 0.0 and match_lens.focal_max not in lens.focal_max:
                    lens.focal_max.append(match_lens.focal_max)
                if match_lens.aperture_min != 0.0 and match_lens.aperture_min not in lens.aperture_min:
                    lens.aperture_min.append(match_lens.aperture_min)
                if match_lens.aperture_max != 0.0 and match_lens.aperture_max not in lens.aperture_max:
                    lens.aperture_max.append(match_lens.aperture_max)

                if (len(lens.aperture_min) == 1 and lens.aperture_min[0] == match_lens.aperture_min 
                    and len(lens.focal_min) == 1 and lens.focal_min[0] == match_lens.focal_min
                    and (len(lens.aperture_max) == 0 and match_lens.aperture_max == 0.0) or (len(lens.aperture_max) == 1 and lens.aperture_max[0] == match_lens.aperture_max)
                    and (len(lens.focal_max) == 0 and match_lens.focal_max == 0.0) or (len(lens.focal_max) == 1 and lens.focal_max[0] == match_lens.focal_max)):
                    print(f'Skipping lens model "{lens.model}" as no mismatch is found')
                    continue
                else:
                    print(f'Lens model "{lens.model}" found in list, collected data')

        option = ask(f'Lens model {lens.model}: 1 - Skip / 2 - Add to invalid list / Other - Add to list')
        if option == '1':
            continue
        if option == '2':
            csv_data.invalid_lenses.append(lens.model)
            continue

        new_lens = complete_lens_data(lens)
        if new_lens is None:
            continue
        csv_data.lenses.append(new_lens)
        csv_data.reload_lookups()

    for cam in col_cam:
        if cam.model == '':
            print(f'Skipping camera as it has no name')
            continue

        cam_name = cam.name()
        if cam_name in csv_data.invalid_cameras:
            print(f'Skipping camera "{cam_name}" as it is in list of invalid cameras')
            continue

        if cam_name in csv_data.lookup_name_to_camera:
            print(f'Skipping camera "{cam_name}" as it already exists')
            continue

        option = ask(f'Camera {cam_name}: 1 - Skip / 2 - Add to invalid list / Other - Add to list')
        if option == '1':
            continue
        if option == '2':
            csv_data.invalid_cameras.append(cam_name)
            continue
        
        new_cam = complete_camera_data(cam)
        if new_cam is None:
            continue
        csv_data.cameras.append(new_cam)
        csv_data.reload_lookups()

    write_csv_data(csv_data)

def run_scan_for_gear(csv_data: CsvData, exif: exiftool.ExifToolHelper):
    dir = ask_directory('Which directory should be scanned?')
    if dir == "":
        return
    node_dirs = perform_scan_and_convert(dir, exif)
    scan_for_gear(node_dirs, csv_data)

# DATA FIXING

def perform_mismatch_autofixes(key_pic_1: str, key_pic_2: str, 
                                val_pic_1: PictureData, val_pic_2: PictureData, 
                                changes_1: Dict[str,str], changes_2: Dict[str,str],
                                diffs: PicDiff, do_pixel_fix: bool):
    if (do_pixel_fix and ((key_pic_1 == '.dng' and key_pic_2 == '.jpg') or (key_pic_1 == '.jpg' and key_pic_2 == '.dng'))
            and val_pic_1.camera.make.lower() == 'google' and val_pic_2.camera.make.lower() == 'google'
            and val_pic_1.camera.model.lower().find('pixel') != -1 and val_pic_2.camera.model.lower().find('pixel') != -1):
        (index_source, changes_target, pic_target) = (1, changes_1, val_pic_1) if key_pic_1 == '.dng' else (0, changes_2, val_pic_2)
        possible_tags = [TAG_PIC_ISO, TAG_PIC_APERTURE, TAG_PIC_EXPOSURE, TAG_LENS_MODEL]

        for possible_tag in possible_tags:
            if possible_tag in diffs:
                print(f'Performing Auto Pixel DNG fix for {possible_tag} ({diffs[possible_tag][1 if index_source == 0 else 0]} -> {diffs[possible_tag][index_source]}) on "{pic_target.path}"')
                changes_target[possible_tag] = diffs[possible_tag][index_source]
                diffs.pop(possible_tag)

def fix_mismatched_groups(node_dirs: NodeDirs, exif: exiftool.ExifToolHelper):
    pixel_dng_fix = ask('Type "1" to automatically fix broken Google Pixel DNG files') == "1"

    for (key_dir, node_groups) in node_dirs.items():
        if ask(f'Press "1" to skip directory "{key_dir}"') == "1":
                continue
        for (key_group, node_pics) in node_groups.items():
            if len(node_pics) <= 1:
                continue

            key_pic_prev = ''
            for (key_pic_2, val_pic_2) in node_pics.items():
                key_pic_1 = key_pic_prev
                key_pic_prev = key_pic_2
                if key_pic_1 == '':
                    continue

                val_pic_1 = node_pics[key_pic_1]
                diffs = val_pic_1.equals(val_pic_2)
                if len(diffs) < 1:
                    continue

                changes_1: Dict[str, str] = dict()
                changes_2: Dict[str, str] = dict()
                perform_mismatch_autofixes(key_pic_1, key_pic_2, val_pic_1, val_pic_2, changes_1, changes_2, diffs, pixel_dng_fix)
                
                if len(diffs) > 0:
                    diffs_formatted = "\n".join([f' - {x}: "{diffs[x][0]}" / "{diffs[x][1]}"' for x in diffs])
                    answer = ask(f'Files in directory "{key_dir}" with name "{key_group}" have mismatching data ("{key_pic_1}" / "{key_pic_2}"):\n{diffs_formatted}\n\n1 - Skip / 2 - Open 1st and pick / 3 - Open 2nd and pick / Other - Pick')
                    if answer != "1":
                        if answer == "2":
                            open_file(val_pic_1.path)
                        elif answer == "3":
                            open_file(val_pic_2.path)
                        
                        for diff in diffs:
                            answer = ask(f'Mismatch "{diff}": "{diffs[diff][0]}" / "{diffs[diff][1]}"\n1 - Keep 1st / 2 - Keep 2nd / Other - Skip')
                            if answer == "1":
                                changes_2[diff] = diffs[diff][0]
                            elif answer == "2":
                                changes_1[diff] = diffs[diff][1]
                
                if len(changes_1) > 0:
                    print(f'Applying {len(changes_1)} changes to {val_pic_1.path}')
                    exif_set_tags(val_pic_1.path, changes_1, exif)
                if len(changes_2) > 0:
                    print(f'Applying {len(changes_2)} changes to {val_pic_2.path}')
                    exif_set_tags(val_pic_2.path, changes_2, exif)

def run_fix_mismatched_groups(exif: exiftool.ExifToolHelper):
    dir = ask_directory('Which directory should be fixed?')
    if dir == "":
        return
    node_dirs = perform_scan_and_convert(dir, exif)
    fix_mismatched_groups(node_dirs, exif)  

# DIRECTORY PROCESSING

def can_fix_check(do_fixes: bool, do_fixes_no_shortcut: bool, do_fixes_shortcut_auto: bool, shortcut: bool, fix_name: str) -> bool:
    if not do_fixes:
        return False
    if not do_fixes_no_shortcut and not shortcut:
        return False
    if do_fixes_shortcut_auto and shortcut:
        return True
    return ask(f'Fix (Press "1" to apply): {fix_name}') == "1"

def add_missing_data(node_dirs: NodeDirs, csv_data: CsvData, exif: exiftool.ExifToolHelper):
    do_fixes = ask('Press "1" to perform fixes for missing data that is available') == "1"
    do_fixes_no_shortcut = do_fixes and ask('Normally fixes are only done if the lens or camera has shortcuts enabled, press "1" to bypass') == "1"
    do_fixes_shorctut_auto = do_fixes and ask('Press "1" to automatically apply fixes if available (only applies when shortcuts are enabled on lens or camera)') == "1"

    helper_lens_text = "Please select a lens:\n" + "\n".join(f' {i+1} > {x.name()}' for i,x in enumerate(csv_data.lookup_shortcut_lens))
    helper_camera_text = "Please select a camera:\n" + "\n".join(f' {i+1} > {x.name()}' for i,x in enumerate(csv_data.lookup_shortcut_camera))

    for (key_dir, node_groups) in node_dirs.items():
        if ask(f'Press "1" to skip directory "{key_dir}"') == "1":
            continue
        for (key_group, node_pics) in node_groups.items():
            if len(node_pics) == 0:
                continue
            pic_base = get_preferred_picture_data(node_pics)
            changes: Dict[str, str] = dict()
            helper_picture_group_text = f'Picture group "{key_group}" ({", ".join(node_pics.keys())})'

            camera_set = False
            if pic_base.camera.model != '' and pic_base.camera.name() not in csv_data.invalid_cameras:
                if pic_base.camera.name() in csv_data.lookup_name_to_camera:
                    pic_base.camera = csv_data.lookup_name_to_camera[pic_base.camera.name()]
                    camera_set = True
                else:
                    option = ask(f'{helper_picture_group_text} has a camera "{pic_base.camera.name()}" that has no match in saved data, press "1" to skip saving or "2" to add to invalid list')
                    if (option == "2"):
                        csv_data.invalid_cameras.append(pic_base.camera.name())
                        write_csv_data(csv_data)
                    elif (option != "1"):
                        new_cam = complete_camera_data(pic_base.camera)
                        if new_cam is not None:
                            csv_data.cameras.append(new_cam)
                            csv_data.reload_lookups()
                            write_csv_data(csv_data)
                            pic_base.camera = new_cam
                            camera_set = True
            
            if not camera_set:
                option = ask(f'{helper_picture_group_text} does not have a valid camera: 1 - Skip / 2 - Open + Assign / Other - Set')
                if option != "1":
                    if option == "2":
                        open_file(pic_base.path)
                    selected = int_or_zero(ask(helper_camera_text))
                    if selected > 0 and selected <= len(csv_data.lookup_shortcut_camera):
                        pic_base.camera = csv_data.lookup_shortcut_camera[selected - 1]
                        if pic_base.camera.is_valid():
                            if pic_base.camera.make != '':
                                changes[TAG_CAM_MAKE] = pic_base.camera.make
                            changes[TAG_CAM_MODEL] = pic_base.camera.model
                            camera_set = True
                        else:
                            print('Invalid camera selected!')
                    else:
                        print('Invalid camera idex!')

            lens_set = False
            if pic_base.lens.model != '' and pic_base.lens.model not in csv_data.invalid_lenses:
                if pic_base.lens.model in csv_data.lookup_model_to_lens:
                    new_lens = csv_data.lookup_model_to_lens[pic_base.lens.model]
                    new_lens_info = new_lens.create_lens_info(True)
                    old_lens_info = pic_base.lens.create_lens_info(False) 
                    if (new_lens_info != old_lens_info
                        and can_fix_check(do_fixes, do_fixes_no_shortcut, do_fixes_shorctut_auto, new_lens.has_shortcut, f'Applying missing Lens Info ({old_lens_info} => {new_lens_info})')):
                        changes[TAG_LENS_INFO] = new_lens_info
                    pic_base.lens = new_lens
                    lens_set = True
                else:
                    option = ask(f'{helper_picture_group_text} has a lens "{pic_base.lens.model}" that has no match in saved data, press "1" to skip saving or "2" to add to invalid list')
                    if (option == "2"):
                        csv_data.invalid_lenses.append(pic_base.lens.model)
                        write_csv_data(csv_data)
                    elif (option != "1"):
                        old_lens = pic_base.lens
                        new_lens = complete_lens_data(ScannedLensData(old_lens.model, old_lens))
                        if new_lens is not None:
                            csv_data.lenses.append(new_lens)
                            csv_data.reload_lookups()
                            write_csv_data(csv_data)
                            if new_lens.create_lens_info(False) != pic_base.lens.create_lens_info(False):
                                changes[TAG_LENS_INFO] = new_lens.create_lens_info(True)
                            pic_base.lens = new_lens
                            lens_set = True

            lens_optional = not camera_set or pic_base.camera.lens_optional
            if not lens_set and not (lens_optional and pic_base.lens.model == ''):
                option = ask(f'{helper_picture_group_text} does not have a valid lens: 1 - Skip / 2 - Open + Assign / Other - Set')
                if option != "1":
                    if option == "2":
                        open_file(pic_base.path)
                    selected = int_or_zero(ask(helper_lens_text))
                    if selected > 0 and selected <= len(csv_data.lookup_shortcut_lens):
                        pic_base.lens = csv_data.lookup_shortcut_lens[selected - 1]
                        if pic_base.lens.is_valid():
                            changes[TAG_LENS_MODEL] = pic_base.lens.model
                            changes[TAG_LENS_INFO] = pic_base.lens.create_lens_info(True)
                            lens_set = True
                        else:
                            print('Invalid lens selected!')
                    else:
                        print('Invalid lens idex!')

            if (pic_base.focal_length == 0.0 and lens_set and pic_base.lens.focal_min == (pic_base.lens.focal_max if pic_base.lens.focal_max > 0.0 else pic_base.lens.focal_min)
                and can_fix_check(do_fixes, do_fixes_no_shortcut, do_fixes_shorctut_auto, pic_base.lens.has_shortcut, f'Applying prime focal length ({pic_base.lens.focal_min})')):
                pic_base.focal_length = pic_base.lens.focal_min
                changes[TAG_PIC_FOCAL] = str(pic_base.lens.focal_min)
                pic_base.focal_length_in_35mm_format = 0
                changes[TAG_PIC_FOCAL35] = "0"

            if (pic_base.focal_length != 0.0 and pic_base.focal_length_in_35mm_format == 0 and camera_set
                and can_fix_check(do_fixes, do_fixes_no_shortcut, do_fixes_shorctut_auto, pic_base.camera.has_shortcut, f'Applying 35mm focal length ({pic_base.focal_length * pic_base.camera.crop})')):
                pic_base.focal_length_in_35mm_format = int(pic_base.focal_length * pic_base.camera.crop)
                changes[TAG_PIC_FOCAL35] = str(pic_base.focal_length_in_35mm_format)

            if len(changes) > 0:
                for (_, pic) in node_pics.items():
                    exif_set_tags(pic.path, changes, exif)

def run_add_missing_data(csv_data: CsvData, exif: exiftool.ExifToolHelper):
    if ask('This tool will alter the exif data of all files within a group, please fix any mismatches before running this. Press "1" to cancel') == "1":
        return
    dir = ask_directory("Which directory should be checked for missing data?")
    if dir == "":
        return
    node_dirs = perform_scan_and_convert(dir, exif)
    add_missing_data(node_dirs, csv_data, exif)

# BULK EDITS

def bulk_edit(node_dirs: NodeDirs, csv_data: CsvData, exif: exiftool.ExifToolHelper):
    mode = ask('What should be bulk edited? 1 - Camera / 2 - Lens / 3 - Photographer')
    changes: PicDiff = dict()

    if mode == '1':
        helper_camera_text = "Please select a camera:\n" + "\n".join(f' {i+1} > {x.name()}' for i,x in enumerate(csv_data.lookup_shortcut_camera))
        selected = int_or_zero(ask(helper_camera_text))
        if selected > 0 and selected <= len(csv_data.lookup_shortcut_camera):
            changes = csv_data.lookup_shortcut_camera[selected - 1].equals(CameraData('', '', 0.0, False, False, False))
        else:
            print('Invalid camera selected!')
            return
        
    elif mode == '2':
        helper_lens_text = "Please select a lens:\n" + "\n".join(f' {i+1} > {x.name()}' for i,x in enumerate(csv_data.lookup_shortcut_lens))
        selected = int_or_zero(ask(helper_lens_text))
        if selected > 0 and selected <= len(csv_data.lookup_shortcut_lens):
            changes = csv_data.lookup_shortcut_lens[selected - 1].equals(LensData('', 0.0, 0.0, 0.0, 0.0, False))
        else:
            print('Invalid lens selected!')
            return

    elif mode == '3':
        name = ask('Provide a photographer name')
        changes[TAG_PIC_PHOTOGRAPHER] = (name, '')

    if len(changes) == 0:
        print('No valid values located, skipping')
        return
    
    changes_transformed: Dict[str,str] = dict()
    for (key, value) in changes.items():
        changes_transformed[key] = value[0]

    for (dir, node_groups) in node_dirs.items():
        if ask(f'Type "1" to apply bulk edit to directory "{dir}"') == '1':
            change_count = 0
            for (_, node_pics) in node_groups.items():
                for (_, node_pic) in node_pics.items():
                    exif_set_tags(node_pic.path, changes_transformed, exif)
                    change_count = change_count + 1
            print(f'Applied changes to {change_count} files')

def run_bulk_edit(csv_data: CsvData, exif: exiftool.ExifToolHelper):
    dir = ask_directory("Which directory should be bulk edited?")
    if dir == "":
        return
    node_dirs = perform_scan_and_convert(dir, exif)
    bulk_edit(node_dirs, csv_data, exif)
    
# OTHER

def run_full(csv_data: CsvData, exif: exiftool.ExifToolHelper):
    dir = ask_directory('Which directory should be processed?')
    if dir == "":
        return

    node_dirs = perform_scan_and_convert(dir, exif)
    csv_data.reload_lookups()
    scan_for_gear(node_dirs, csv_data)
    fix_mismatched_groups(node_dirs, exif)
    node_dirs = perform_scan_and_convert(dir, exif)
    csv_data.reload_lookups()
    while 1==1:
        if ask('Press "1" to perform a bulk edit') == '1':
            bulk_edit(node_dirs, csv_data, exif)
            node_dirs = perform_scan_and_convert(dir, exif)
        else:
            break
    add_missing_data(node_dirs, csv_data, exif)

# ANALYTICS

COL_FILE_PATH = 'File_Path'
COL_FILE_FOLDER = 'File_Folder'

COL_CAM_MAKE = 'Cam_Make'
COL_CAM_MODEL = 'Cam_Model'

COL_LENS_MODEL = 'Lens_Model'
COL_LENS_FOCAL_MIN = 'Lens_FocalMin'
COL_LENS_FOCAL_MAX = 'Lens_FocalMax'
COL_LENS_APER_MIN = 'Lens_AperMin'
COL_LENS_APER_MAX = 'Lens_AperMax'

COL_PIC_FOCAL = 'Pic_Focal'
COL_PIC_FOCAL35 = 'Pic_Focal35'
COL_PIC_ISO = 'Pic_Iso'
COL_PIC_EXPO = 'Pic_Expo'
COL_PIC_APER = 'Pic_Aper'
COL_PIC_CREAT = 'Pic_Creat'
COL_PIC_PHOTO = 'Pic_Photo'

COLS_STR: List[str] = [COL_FILE_FOLDER, COL_CAM_MAKE, COL_CAM_MODEL, COL_LENS_MODEL, COL_PIC_PHOTO]
COLS_FLOAT: List[str] = [COL_LENS_FOCAL_MIN, COL_LENS_FOCAL_MAX, COL_LENS_APER_MIN, COL_LENS_APER_MAX, COL_PIC_FOCAL, COL_PIC_EXPO, COL_PIC_APER]
COLS_INT: List[str] = [COL_PIC_FOCAL35, COL_PIC_ISO]
COLS_DATE: List[str] = [COL_PIC_CREAT]

def ask_for_column(action: str, exclude_str: bool = False) -> str | None:
    options: Dict[str,tuple[str,List[str]]] = dict([
        ("1", ('Strings', COLS_STR)),
        ("2", ('Floats', COLS_FLOAT)),
        ("3", ('Ints', COLS_INT)),
        ("4", ('Dates', COLS_DATE))
    ])
    displayOpts = [f' {kvp[0]} > {kvp[1][0]}: {', '.join(kvp[1][1])}' for kvp in options.items()]
    type = ask(f'Select a type for {action}:\n{'\n'.join(displayOpts)}')
    if type not in options:
        print('Invalid type!')
        return None
    if exclude_str and type == '1':
        print('String columns can not be used for this')
        return None
    selected_cols = options[type][1]

    displaySubopts = [f' {idx + 1} > {val}' for (idx, val) in enumerate(selected_cols)]
    col = int_or_zero(ask(f'Select a row for {action}:\n{'\n'.join(displaySubopts)}'))
    if col < 1 or col > len(selected_cols):
        print('Invalid row!')
        return None
    return selected_cols[col - 1]

def get_filtered_by_column(curr_data_frame: pd.DataFrame) -> pd.DataFrame | None:
    col = ask_for_column('filtering')
    if col is None:
        return None

    if col in COLS_STR:
        col_unique_vals = curr_data_frame[col].unique()
        if len(col_unique_vals) == 0:
            print('No values found in column')
            return None
        display_unique_vals = [f' {idx + 1} > {val}' for (idx, val) in enumerate(col_unique_vals)]
        selected_unique_idx_raw = ask(f'Please pick the values to select or exclude (select multiple: 1|2|...):\n{'\n'.join(display_unique_vals)}')
        selected_unique_idx_clean = set(y for y in [int_or_zero(x) for x in selected_unique_idx_raw.split("|")] if y > 0 and y <= len(col_unique_vals))
        if len(selected_unique_idx_clean) == 0:
            print('No valid value found')
            return None
        selected_unique_values = [col_unique_vals[idx - 1] for idx in selected_unique_idx_clean]
        if ask(f'Following were selected ("1" to confirm): {'\n'.join(selected_unique_values)}') != "1":
            return None
        if ask('Default filtering mode is "Filter By", press "1" to instead exclude') == "1":
            return curr_data_frame[~curr_data_frame[col].isin(selected_unique_values)]
        else:
            return curr_data_frame[curr_data_frame[col].isin(selected_unique_values)]

    if col in COLS_FLOAT or col in COLS_INT or col in COLS_DATE:
        col_val_max = curr_data_frame[col].max()
        col_val_min = curr_data_frame[col].min()
        selected_range_raw = ask(f'Values range between {col_val_min} and {col_val_max}, please select a value to select or exclude (range inclusive: min|max, date format=yyyy:mm:dd hh:mm:ss)')
        selected_range_split = selected_range_raw.split('|')
        selected_range_clean = [float_or_zero(x) for x in selected_range_split] if col in COLS_FLOAT else [int_or_zero(x) for x in selected_range_split] if col in COLS_INT else [datetime_or_min(x) for x in selected_range_split]
        if len(selected_range_clean) == 0:
            print('No valid value found')
            return None
        if len(selected_range_clean) > 2:
            print('Too many values found')
            return None
        if len(selected_range_clean) > 1 and selected_range_clean[0] > selected_range_clean[1]:
            selected_range_clean_temp = selected_range_clean[0]
            selected_range_clean[0] = selected_range_clean[1]
            selected_range_clean[1] = selected_range_clean_temp
        if ask(f'Following was selected ("1" to confirm): {selected_range_clean[0] if len(selected_range_clean) == 1 else f'{selected_range_clean[0]} to {selected_range_clean[1]}'}') != "1":
            return None
        if ask('Default filtering mode is "Between", press "1" to instead exclude') == "1":
            if len(selected_range_clean) == 1:
                return curr_data_frame[curr_data_frame[col].ne(selected_range_clean[0])]
            else:
                return curr_data_frame[curr_data_frame[col].lt(selected_range_clean[0]) | curr_data_frame[col].gt(selected_range_clean[1])]
        else:
            if len(selected_range_clean) == 1:
                return curr_data_frame[curr_data_frame[col].eq(selected_range_clean[0])]
            else:
                return curr_data_frame[(curr_data_frame[col].gt(selected_range_clean[0]) | curr_data_frame[col].eq(selected_range_clean[0])) & (curr_data_frame[col].lt(selected_range_clean[1]) | curr_data_frame[col].eq(selected_range_clean[1]))]

    else:
        print('Unable to designate column to a type')
        return None

def analyze_data(node_dirs: NodeDirs):
    data_dict = []
    for (key_dict, node_groups) in node_dirs.items():
        for (_, node_pics) in node_groups.items():
            pic = get_preferred_picture_data(node_pics)
            data_dict.append({
                COL_FILE_PATH: pic.path,
                COL_FILE_FOLDER: key_dict,

                COL_CAM_MAKE: pic.camera.make,
                COL_CAM_MODEL: pic.camera.model,

                COL_LENS_MODEL: pic.lens.model,
                COL_LENS_FOCAL_MIN: pic.lens.focal_min,
                COL_LENS_FOCAL_MAX: pic.lens.focal_max,
                COL_LENS_APER_MIN: pic.lens.aperture_min,
                COL_LENS_APER_MAX: pic.lens.aperture_max,

                COL_PIC_FOCAL: pic.focal_length,
                COL_PIC_EXPO: pic.exposure_time,
                COL_PIC_APER: pic.aperture,
                COL_PIC_FOCAL35: pic.focal_length_in_35mm_format,
                COL_PIC_ISO: pic.iso,
                COL_PIC_CREAT: pic.created,
                COL_PIC_PHOTO: pic.photographer
            })

    main_data_frame = pd.DataFrame(data_dict)
    snapshot_frames: Dict[str, pd.DataFrame] = dict()
    curr_data_frame = main_data_frame.copy()
    while(True):
        opt = ask(f'Currently analyzing Dataset with {len(curr_data_frame)} rows and {len(snapshot_frames)} snapshots\n\n 1 - Filter / 2 - Top / 3 - Graph / 4 - Snapshot or Reset / 5 - Exit')

        if opt == "1":
            new_frame = get_filtered_by_column(curr_data_frame)
            if new_frame is not None:
                if ask(f'Filter result has {len(new_frame)} rows, enter "1" to apply') == "1":
                    curr_data_frame = new_frame

        elif opt == "2":
            col_order = ask_for_column('ordering', True)
            if col_order is None:
                continue
            row_count = int_or_zero(ask('How many elements should be shown?'))
            if row_count < 1:
                print('Invalid row count')
                continue

            order_asc = ask('By default the top elements will be shown, enter "1" to show bottom elements instead') == "1"
            frame_ordered = curr_data_frame.sort_values(col_order, ascending=order_asc).head(row_count)
            for (idx, val) in enumerate(frame_ordered.iterrows()):
                print(f' {idx + 1} > {val[1][col_order]} ({val[1][COL_FILE_PATH]})')
            ask('Enter anything to continue')

        elif opt == "3":
            graph = ask('What graph should be used? 1 - Count Plot / 2 - Count Bars / 3 - Scatter')
            if graph == "1":
                col1 = ask_for_column('Count Plot', True)
                if col1 is None:
                    continue
                plot_data = curr_data_frame.copy()
                ticks = None
                if col1 in COLS_INT:
                    smoothing = int_or_zero(ask('Type a value for grouping intervals (int, rounded)'))
                    if smoothing > 0:
                        plot_data[col1] = plot_data[col1].apply(lambda x: int(float(x)/smoothing)*smoothing)
                    ticks_raw = int_or_zero(ask('Enter a tick interval'))
                    ticks = range_graph_int(plot_data[col1].min(), plot_data[col1].max(), ticks_raw) if ticks_raw > 0 else None
                elif col1 in COLS_FLOAT:
                    smoothing = float_or_zero(ask('Type a value for grouping intervals (float)'))
                    if smoothing > 0:
                        plot_data[col1] = plot_data[col1].apply(lambda x: round(x/smoothing)*smoothing)
                    ticks_raw = float_or_zero(ask('Enter a tick interval'))
                    ticks = range_graph_float(plot_data[col1].min(), plot_data[col1].max(), ticks_raw) if ticks_raw > 0 else None
                plot = plot_data.groupby(col1)[col1].count().plot(kind='line', grid=True, xticks=ticks, ylabel='Count')
                for (idx, label) in enumerate(plot.axes.xaxis.get_ticklabels()):
                    if idx % 2 == 1:
                        label.set_visible(False)
                    else:
                        label.set_fontsize(4)
                        label.set_rotation('vertical')
                plot.get_figure().savefig(FIGURE)
                open_file(FIGURE)

            elif graph == "2":
                col1 = ask_for_column('Count Bars', True)
                if col1 is None:
                    continue
                plot_data = curr_data_frame.copy()
                if col1 in COLS_INT:
                    smoothing = int_or_zero(ask('Type a value for grouping intervals (int, rounded)'))
                    if smoothing > 0:
                        plot_data[col1] = plot_data[col1].apply(lambda x: int(float(x)/smoothing)*smoothing)
                elif col1 in COLS_FLOAT:
                    smoothing = float_or_zero(ask('Type a value for grouping intervals (float)'))
                    if smoothing > 0:
                        plot_data[col1] = plot_data[col1].apply(lambda x: round(x/smoothing)*smoothing)
                plot = plot_data.groupby(col1)[col1].count().plot(kind='bar', ylabel='Count')
                for label in plot.axes.xaxis.get_ticklabels():
                    label.set_fontsize(4)
                    label.set_rotation('vertical')
                plot.get_figure().savefig(FIGURE)
                open_file(FIGURE)

            elif graph == "3":
                col1 = ask_for_column('Scatter X Axis', True)
                if col1 is None:
                    continue
                log1 = ask('Type "1" to do log scaling on X') == "1"
                col2 = ask_for_column('Scatter Y Axis', True)
                if col2 is None:
                    continue
                log2 = ask('Type "1" to do log scaling on Y') == "1"
                col3 = None
                if ask('Type "1" to add a Z Axis') == "1":
                    col3 = ask_for_column('Scatter Z Axis', False)
                    if col3 is None:
                        continue
                plot = curr_data_frame.plot.scatter(x=col1, y=col2, c=col3)
                plot.set_xscale('log' if log1 else 'linear')
                plot.set_yscale('log' if log1 else 'linear')
                for label in plot.get_legend().get_texts():
                    label.set_fontsize(3)
                plot.get_figure().savefig(FIGURE)
                open_file(FIGURE)

            else:
                print('Unknown graph type')
                continue

        elif opt == "4":
            mode = ask('What would you like to do? 1 - Reset / 2 - Load Snapshot / 3 - Create Snapshot / 4 - Remove Snapshot')
            if mode == "1":
                curr_data_frame = main_data_frame.copy()

            elif mode == "2":
                sel_key = ask(f'Which snapshot would you like to load?\n{'\n'.join(f' - {key}' for key in snapshot_frames.keys())}')
                if sel_key in snapshot_frames:
                    curr_data_frame = snapshot_frames[sel_key]
                else:
                    print('Invalid snapshot')

            elif mode == "3":
                sel_key = ask(f'What should the snapshot be named?')
                if sel_key != '':
                    if sel_key in snapshot_frames:
                        print('A snapshot with this name alredy exists')
                    else:
                        snapshot_frames[sel_key] = curr_data_frame

            elif mode == "4":
                sel_key = ask(f'Which snapshot would you like to delete?\n{'\n'.join(f' - {key}' for key in snapshot_frames.keys())}')
                if sel_key in snapshot_frames:
                    snapshot_frames.pop(sel_key)
                else:
                    print('Invalid snapshot')

            else:
                print('Invalid option!')
        
        elif opt == "5":
            break
        else:
            print('Invalid option!')

def run_analze_data(exif: exiftool.ExifToolHelper):
    if ask('This tool will analyze only one of the files within a group, please fix any mismatches before running this. Press "1" to cancel') == "1":
        return
    dir = ask_directory("Which directory should be analyzed?")
    if dir == "":
        return
    node_dirs = perform_scan_and_convert(dir, exif)
    analyze_data(node_dirs)
    
# LOGIC BEGINS

def main():
    csv_data = load_csv_data()
    with exiftool.ExifToolHelper() as exif:
        while True:
            menuInput = ask('Welcome to ImageMetadataFixer!\n\n 1 > Scan for Cameras/Lenses\n 2 > Fix group mismatches \n 3 > Add missing data\n 4 > Full Process\n 5 > Bulk Edit\n 6 > Analyze\n 7 > Exit')

            if (menuInput == '1'):
                csv_data.reload_lookups()
                run_scan_for_gear(csv_data, exif)
            elif (menuInput == '2'):
                run_fix_mismatched_groups(exif)
            elif (menuInput == '3'):
                csv_data.reload_lookups()
                run_add_missing_data(csv_data, exif)
            elif (menuInput == '4'):
                run_full(csv_data, exif)
            elif (menuInput == '5'):
                run_bulk_edit(csv_data, exif)
            elif (menuInput == '6'):
                run_analze_data(exif)
            elif (menuInput == '7'):
                print('Goodbye!')
                break
            else:
                print('Invalid option supplied!')

main()