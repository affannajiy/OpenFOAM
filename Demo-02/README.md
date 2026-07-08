- The directory `constant/orig_triSurface` contains the user provided stl files without any change in names. This has to remain.

- Copy
```
cp constant/orig_triSurface constant/triSurface
```

- Open the `tools/geometry_renamer.html` file in Google Chrome > Browse and Upload the triSurface folder containing the stl files

- Make encoding changes (Encoding on/off, auto refinement on/off, Surface type: Boundary/faceZone, Whether cellZone, Vol. refinement etc etc)

- Click on `Copy to Clipboard` button > Go to the triSurface directory in your linux terminal > Paste and hit enter > Files are renamed!

- Go to the case directory: `cd ../../` and paste the copied contents in the terminal

- Save the geometric files list to a new file: 
```
ls -1 constant/triSurface/ > geom_files.txt
```

- Make changes to `snappy_inputs.json` file as required.

- Run the `setup_snappy.py` script with python3 > `blockMeshDict` and `snappyHexMeshDict` will be generated
 
- WARNING: This point is just for information and don't do it unless necessary. If you want to delete the folder for other purpose, follow the following:
```
chmod -R u+w constant/orig_triSurface
rm -rf constant/orig_triSurface
```
