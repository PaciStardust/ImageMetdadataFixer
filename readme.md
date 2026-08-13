# ImageMetadataFixer
A simple tool for managing my image library
- Loads metadata from folders and groups raw and jpeg
- Collects Lens and Camera and Film information
- Allows for correction of mismatched and missing data
- Simple analysis of image data
- **Note:** Film data is stored in the EXIF Software field

## CSV Layouts

### Camera Data (`cam.csv`)
```
camera_make,camera_model,camera_crop_factor,camera_shortcut(0/1),lens_optional(0/1),is_film(1/0)
```
#### Example:
```
SONY,ILCE-6400,1.5,1,0,0
Olympus,XA,1.0,1,0,1
```

### Lens Data (`lens.csv`)
```
lens_model,focal_min,focal_max,aperture_min,aperture_max,lens_shortcut(0/1)
```
#### Example:
```
E 18-135mm F3.5-5.6 OSS,18.0,135.0,3.5,5.6,1
Olympus F. Zuiko,35.0,35.0,2.8,2.8,1
```

### Invalid Cameras (`inv_cam.csv`)
```
camera_full_name
```
#### Example:
```
Minolta EZ Controller
```

### Invalid Lenses (`inv_lens.csv`)
```
lens_name
```
#### Example:
```
----
```

### Film Data (`film.csv`)
```
film_name,iso
```
#### Example:
```
Kodak Gold 200,200
Kodak Kodacolor 200,200
```

### Film Scan Locations (`loc.csv`)
```
location name
```
#### Example:
```
Eastman Kodak
```