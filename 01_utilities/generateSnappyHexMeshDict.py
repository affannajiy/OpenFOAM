#!/usr/bin/env python3
"""
Filename: generateSnappyHexMeshDict.py
Author: G. Vijaya Kumar
Date: November 30, 2024
Description: Generate snappyHexMeshDict
Compatible with: ESI OpenFOAM-v2312

Instructions: 
1. The OpenFOAM environment should be sourced first
2. The surface files should be in .stl file
3. Edge files can be all supported OpenFOAM formats
4. If you want a separate cellZone (or region for CHT), it should be from a 
   separate stl file with the correct normal orientations.
5. Only finalAndExpansion mode is supported now for layer addition
6. Only the meshShrinker :displacementMotionSolver is allowed and all necessary
    settings, fvSchemes and fvSolution files will be automatically created.
7. For multiregion setups, choose the patch wisely for layer addition
    e.g., based on the stl orientation it can be just <name> or <name>_slave
"""

import os
import subprocess
import argparse
import sys

def execute_command(command):
    """
    Executes a shell command and handles the output.
    :param command: Command string to be executed.
    """
    try:
        result = subprocess.run(command, text=True, capture_output=True, shell=True)
        if not (result.returncode == 0):
            print("Command failed with error:")
            print(result.stderr)
    except FileNotFoundError:
        print(f"Command not found: {command}")
    except Exception as e:
        print(f"An unexpected error occurred while executing command: {e}")

def get_boolean_input(prompt):
    """
    Prompt the user for a boolean response (True/False).
    :param prompt: The question to display to the user.
    :return: True for 'true', False for 'false'.
    """
    while True:
        response = input(prompt + " yes (y/Y) or no (n/N): ").strip().lower()
        if response in ["true", "t", "yes", "y", "1", "Y"]:
            return True
        elif response in ["false", "f", "no", "n", "0", "N"]:
            return False
        else:
            print("Invalid input. Please type 'true' or 'false'.")

def get_vector(prompt):
    """
    Prompt the user for a 3-component vector and return it as a string in the format "(x y z)".
    :param prompt: The message to display to the user.
    :return: A string representing the vector in the format "(x y z)".
    """
    while True:
        try:
            user_input = input(prompt + " x y z: ").strip()
            components = user_input.split()
            
            # Ensure exactly 3 components are provided
            if len(components) != 3:
                raise ValueError("You must enter exactly 3 components.")
            
            # Convert components to floats to validate them as numbers
            components = [float(component) for component in components]
            
            # Format the vector as a string
            return f"({components[0]} {components[1]} {components[2]})"
        except ValueError as e:
            print(f"Invalid input: {e}. Please try again.")

def list_files(directory):
    """
    List all files in a directory.
    :param directory: Path to the directory.
    :return: List of file names.
    """
    try:
        if not os.path.exists(directory):
            raise FileNotFoundError(f"The directory '{directory}' does not exist.")
        
        files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
        if not files:
            raise FileNotFoundError(f"No files found in the directory '{directory}'.")
        
        return files
    except FileNotFoundError as e:
        print(e)
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def get_stl_zone_names(stl_file_path):
    """
    Extract the names of zones from an ASCII STL file.
    :param stl_file_path: Path to the STL file.
    :return: A list of zone names.
    """
    try:
        with open(stl_file_path, 'r') as file:
            lines = file.readlines()
        
        zone_names = []
        for line in lines:
            stripped_line = line.strip().lower()
            if stripped_line.startswith("solid"):
                # Extract the zone name (everything after 'solid')
                parts = line.strip().split(maxsplit=1)
                if len(parts) > 1:  # Check if there's a name after 'solid'
                    zone_names.append(parts[1])
                else:
                    zone_names.append("Unnamed Zone")  # Default for unnamed zones
        
        if zone_names:
            return zone_names
        else:
            return "No zones found in the STL file."
    except FileNotFoundError:
        return f"File not found: {stl_file_path}"
    except Exception as e:
        return f"An error occurred: {e}"

def get_min_max(prompt):
    """
    Prompt the user with a custom message to enter two integers separated by a space 
    and return them as min and max values.
    
    :param prompt: Custom prompt message for the user.
    :return: A tuple (min_val, max_val) if valid input, or None if invalid.
    """
    min_max_input = input(prompt)

    try:
        min_val, max_val = map(int, min_max_input.split())
        return min_val, max_val
    except ValueError:
        print("Invalid input. Please enter two integers separated by a space.")
        return None

def get_boundary_type():
    """
    Prompt the user for an integer and return two corresponding strings based on the input.
    :return: A tuple of two strings or an error message.
    """
    single_mapping = {
        1: "wall",
        2: "patch",
        3: "faceZone"
    }

    plural_mapping = {
        1: "walls",
        2: "patches",
        3: "faceZones"
    }

    try:
        user_input = int(input("Enter boundary type: 1 (wall) or 2 (patch) or 3 (faceZone): "))
        single_result = single_mapping.get(user_input, "Invalid input")
        plural_result = plural_mapping.get(user_input, "Invalid input")

        if single_result == "Invalid input":
            return "Invalid input"
        return single_result, plural_result

    except ValueError:
        return "Invalid input. Please enter an integer."

def write_file(directory, filename, content):
    """
    Create or overwrite a file in the specified directory with the given content.
    
    :param directory: The directory where the file should be created.
    :param filename: The name of the file to create or overwrite.
    :param content: The content to write into the file.
    """
    # Construct the full file path
    file_path = os.path.join(directory, filename)

    # Check if the directory exists
    if not os.path.exists(directory):
        print(f"Error: The directory '{directory}' does not exist.")
        return

    # Inform the user about overwriting if the file exists
    if os.path.exists(file_path):
        print(f"The file '{file_path}' already exists and will be overwritten.")

    # Write the content to the file
    with open(file_path, "w") as file:
        file.write(content)

    print(f"The file '{file_path}' has been created/overwritten successfully.")

# Define the system folder and required files
system_folder = "system"
control_dict_file = os.path.join(system_folder, "controlDict")
snappy_hex_mesh_dict_file = os.path.join(system_folder, "snappyHexMeshDict")

try:
    # Check if the system folder exists
    if not os.path.exists(system_folder):
        raise FileNotFoundError(f"The directory '{system_folder}' does not exist.")
    
    # Check if controlDict file exists in the system folder
    if not os.path.isfile(control_dict_file):
        raise FileNotFoundError(f"The required file 'controlDict' is missing in the '{system_folder}' directory.")
    
    # Check if snappyHexMeshDict already exists
    if os.path.isfile(snappy_hex_mesh_dict_file):
        print("Warning: 'snappyHexMeshDict' will be overwritten by the current program.")
    
    # Create or overwrite the snappyHexMeshDict file
    with open(snappy_hex_mesh_dict_file, "w") as file:
        file.write("/*--------------------------------*- C++ -*----------------------------------*\\\n")
        file.write("| =========                 |                                                 |\n")
        file.write("| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n")
        file.write("|  \\\\    /   O peration     | Version:  v2312                                 |\n")
        file.write("|   \\\\  /    A nd           | Website:  www.openfoam.com                      |\n")
        file.write("|    \\\\/     M anipulation  |                                                 |\n")
        file.write("\\*---------------------------------------------------------------------------*/\n")
        file.write("FoamFile\n")
        file.write("{\n")
        file.write("\tversion     2.0;\n")
        file.write("\tformat      ascii;\n")
        file.write("\tclass       dictionary;\n")
        file.write("\tobject      snappyHexMeshDict;\n")
        file.write("}\n")
        file.write("// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n")
        file.write("\n")
    
    execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMesh -add true")
    execute_command("foamDictionary system/snappyHexMeshDict -entry snap -add true")
    execute_command("foamDictionary system/snappyHexMeshDict -entry addLayers -add false")

    execute_command("foamDictionary system/snappyHexMeshDict -entry geometry -add \"{}\"")
    execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls -add \"{}\"")
    execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls -add \"{}\"")
    execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls -add \"{}\"")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls -add \"{}\"")

    execute_command("foamDictionary system/snappyHexMeshDict -entry mergeTolerance -add 1e-6")
    
    print("\n===========================================")
    print("Geometry inputs")
    print("===========================================")
    geometry_folder = "constant/triSurface"
    geom_files = list_files(geometry_folder)
    
    print("\nGeometric files in constant/triSurface directory:")
    for i, file in enumerate(geom_files, start=1):
        print(f"{i}. {file}")
    
    # Get surface files from user input
    surface_input = input("\nSurface files in this list (numbers separated by spaces): ").strip()
    edge_input = input("Edge files in this list (numbers separated by spaces): ").strip()
    
    surface_files=[]
    edge_files=[]
    geometry_region_names = []  # contains region names from user defined files in the geometry dict
    region_zone_list = []       # containes zone names inside the user defined files
    special_region_names = []   # contains region names of standard shapes defined in the geometry dict
    combined_region_names = []  # Combines geometry_region_names and special_region_names
    volume_refinement_region_names = [] # To store regions requiring a different refinement level

    try:
        surface_indices = [int(num) for num in surface_input.split()]
        edge_indices = [int(num) for num in edge_input.split()]
        
        # Map indices to file names
        surface_files = [geom_files[i - 1] for i in surface_indices]
        edge_files = [geom_files[i - 1] for i in edge_indices]

        if not set(surface_files).isdisjoint(set(edge_files)):
            sys.exit("Surface files and Edge files should be mutually exclusive!")
    except (ValueError, IndexError):
        print("Invalid input. Please ensure you enter valid numbers corresponding to the file list.")

    for ii in range(len(surface_files)):
        stl_region_name = os.path.splitext(surface_files[ii])[0] # removing suffix .stl
        execute_command("foamDictionary system/snappyHexMeshDict -entry geometry/"+surface_files[ii]+" -add \"{}\"")
        execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{surface_files[ii]}/type -add triSurfaceMesh")
        execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{surface_files[ii]}/name -add {stl_region_name}")
        surface_file_path = os.path.join(geometry_folder, surface_files[ii])
        zone_names = get_stl_zone_names(surface_file_path)
        num_zones = len(zone_names)
        if(num_zones > 1):
            execute_command("foamDictionary system/snappyHexMeshDict -entry geometry/"+surface_files[ii]+"/regions"+" -add \"{}\"")
            for jj in range(num_zones):
                execute_command("foamDictionary system/snappyHexMeshDict -entry geometry/"+surface_files[ii]+"/regions/"+zone_names[jj]+" -add \"{}\"")
                execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{surface_files[ii]}/regions/{zone_names[jj]}/name -add {zone_names[jj]}")
        geometry_region_names.append(stl_region_name)    
        combined_region_names.append(stl_region_name)
        region_zone_list.append(zone_names)
    
    num_special_regions = int(input("\nEnter the number of additional standard shapes for volume refinement or separate cellZones (0 for no extra shapes): "))
    for ii in range(num_special_regions):
        special_region_names.append("shape_"+str(ii+1))
        combined_region_names.append("shape_"+str(ii+1))
        print(f"\nDetails of shape_{ii+1}:")
        special_region_type = int(input("Available shapes are\n1 (box)\n2 (cylindrical)\n3 (sphere)\nEnter the type: "))
        execute_command("foamDictionary system/snappyHexMeshDict -entry geometry/"+special_region_names[ii]+" -add \"{}\"")
        if(special_region_type == 1):
            min_point = get_vector("Enter box's min point ")
            max_point = get_vector("Enter box's max point ")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/type -add searchableBox")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/min -add \"{min_point}\"")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/max -add \"{max_point}\"")
        elif(special_region_type == 2):
            center_point_1 = get_vector("Enter axis starting point ")
            outer_radius_1 = float(input("Outer radius at axis start: "))
            inner_radius_1 = float(input("Inner radius at axis start: "))
            center_point_2 = get_vector("Enter axis ending point ")
            outer_radius_2 = float(input("Outer radius at axis start: "))
            inner_radius_2 = float(input("Inner radius at axis start: "))
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/type -add searchableCone")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/point1 -add \"{center_point_1}\"")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/radius1 -add {outer_radius_1}")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/innerRadius1 -add {inner_radius_1}")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/point2 -add \"{center_point_2}\"")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/radius2 -add {outer_radius_2}")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/innerRadius2 -add {inner_radius_2}")
        elif(special_region_type == 3):
            centre = get_vector("Centre of the sphere ")
            radius = float(input("Radius of the sphere: "))
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/type -add searchableSphere")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/centre -add \"{centre}\"")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry geometry/{special_region_names[ii]}/radius -add {radius}")
        else:
            sys.exit("Invalid choice!")


    #--------------------------------
    # castellatedMeshControls section
    #--------------------------------
    execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/maxLocalCells -add 100000000")
    execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/maxGlobalCells -add 300000000")
    execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/minRefinementCells -add 10")
    execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/maxLoadUnbalance -add 0.1")

    print("\n===========================================")
    print("Castellation and refinement related inputs")
    print("===========================================")

    # features - refinement level
    #--------------------------------------------------------------------------------------------------
    print("\nRefinement settings for feature edges")
    print("-------------------------------------")
    
    with open(snappy_hex_mesh_dict_file, "r") as file:
        lines = file.readlines()
    
    modified_lines = []
    inside_castellated_section = False

    for line in lines:
        stripped_line = line.strip()
        modified_lines.append(line)

        # Detect the start of 'castellatedMeshControls' section
        if stripped_line.startswith("castellatedMeshControls"):
            inside_castellated_section = True

        # Detect the end of 'castellatedMeshControls' section
        if inside_castellated_section and stripped_line == "}":
            # Append the 'features' section before the closing brace
            modified_lines.insert(-1, "    features\n")
            modified_lines.insert(-1,"    (\n")
            for ii in range(len(edge_files)):
                modified_lines.insert(-1,"        {\n")
                modified_lines.insert(-1,f"        file    \"{edge_files[ii]}\";\n")
                edge_ref_level = int(input(f"Enter refinement level for {edge_files[ii]}: "))
                modified_lines.insert(-1,f"        level    {edge_ref_level};\n")
                modified_lines.insert(-1,"        }\n")
            modified_lines.insert(-1,"    );\n")
            inside_castellated_section = False  # Exit the section
    #--------------------------------------------------------------------------------------------------
    # END OF features - refinement level
    
    # Write back the modified content
    with open(snappy_hex_mesh_dict_file, "w") as file:
        file.writelines(modified_lines)    

    print("\nVolume refinement")
    print("-----------------\n")
    print("The volume regions are ")
    for ii, reg_name in enumerate(combined_region_names, start=1):
        print(f"{ii}. {reg_name}")

    vol_ref_input = input("\nSelect volume regions with specific refinement levels (numbers separated by spaces): ").strip()

    try:
        vol_ref_reg_indices = [int(num) for num in vol_ref_input.split()]
        
        # Map indices to combined_region_names
        volume_refinement_region_names = [combined_region_names[i - 1] for i in vol_ref_reg_indices]
    except (ValueError, IndexError):
        print("Invalid input. Please ensure you enter valid numbers corresponding to the region list.")

    execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions -add \"{}\"")
    
    for ii in range(len(combined_region_names)):
        ref_level = 0
        if combined_region_names[ii] in volume_refinement_region_names:
            ref_level = int(input(f"Enter volume refinement level inside \"{combined_region_names[ii]}\": "))
        execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/"+combined_region_names[ii]+" -add \"{}\"")
        execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/{combined_region_names[ii]}/mode -add inside")
        execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/{combined_region_names[ii]}/levels -add \"((1.0 {ref_level}))\"")

    #------------refinementRegions -> gap refinement-----------------#
    for ii in range(len(geometry_region_names)):
        gap_refinement = get_boolean_input(f"\nResolve small gaps with a finer refinement level in \"{geometry_region_names[ii]}\" ? ")
        if gap_refinement:
            num_gap_cells = int(input("Enter the minimum number of cells between two surfaces forming a gap (3 (minimum), 4 (recommended): "))   
            level_start = int(input("Grid level at which to start detecting the gaps (usually 0): "))
            max_ref_level = int(input("Maximum allowed refinement level to resolve gaps: "))
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/{geometry_region_names[ii]}/gapLevel -add \"({num_gap_cells} {level_start} {max_ref_level})\"")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/{geometry_region_names[ii]}/gapMode -add mixed")

    print("\nSurface refinement")
    print("------------------")
    execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces -add \"{}\"")
    
    standalone_surfaces = []
    layer_surfaces = [] # boundary names for layer addition process
    for ii in range(len(geometry_region_names)):
        zone_names = region_zone_list[ii]
        if(len(zone_names) > 1):
            execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/"+geometry_region_names[ii]+" -add \"{}\"")
            min_level, max_level = get_min_max(f"\nEnter the global surface refinement levels for \"{geometry_region_names[ii]}\"- min max: ")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{geometry_region_names[ii]}/level -add \"({min_level} {max_level})\"")
            execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/"+geometry_region_names[ii]+"/regions"+" -add \"{}\"")
            for jj in range(len(zone_names)):
                execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/"+geometry_region_names[ii]+"/regions/"+zone_names[jj]+" -add \"{}\"")
                min_level, max_level = get_min_max(f"\nEnter local surface refinement levels for the boundary \"{zone_names[jj]}\"- min max: ") 
                boundary_type, group_type = get_boundary_type()
                execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{geometry_region_names[ii]}/regions/{zone_names[jj]}/level -add \"({min_level} {max_level})\"")
                execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/"+geometry_region_names[ii]+"/regions/"+zone_names[jj]+"/patchInfo"+" -add \"{}\"")
                execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{geometry_region_names[ii]}/regions/{zone_names[jj]}/patchInfo/type -add {boundary_type}")
                execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{geometry_region_names[ii]}/regions/{zone_names[jj]}/patchInfo/inGroups -add \"({group_type})\"")
                layer_surfaces.append(zone_names[jj])
                
        else:
            standalone_surfaces.append(geometry_region_names[ii])
     
    # concatenate single zone regions of geometry_region_names and special_region_names
    standalone_surfaces.extend(special_region_names)

    for ii in range(len(standalone_surfaces)):
        if get_boolean_input(f"\nDo you want to define surface refinement levels and/or patch/wall/faceZone definitions for \"{standalone_surfaces[ii]}\" ?"):
            min_level, max_level = get_min_max(f"Enter surface refinement levels for surface \"{standalone_surfaces[ii]}\"- min max: ")
            boundary_type, group_type = get_boundary_type()
            execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/"+standalone_surfaces[ii]+" -add \"{}\"")
            execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{standalone_surfaces[ii]}/level -add \"({min_level} {max_level})\"")
            if (boundary_type == "wall" or boundary_type == "patch"):
                execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/"+standalone_surfaces[ii]+"/patchInfo"+" -add \"{}\"")
                execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{standalone_surfaces[ii]}/patchInfo/type -add {boundary_type}")
                execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{standalone_surfaces[ii]}/patchInfo/inGroups -add \"({group_type})\"")
                layer_surfaces.append(standalone_surfaces[ii])
            if boundary_type == "faceZone":
                execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{standalone_surfaces[ii]}/faceZone -add {standalone_surfaces[ii]}")
                execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{standalone_surfaces[ii]}/faceType -add internal")
                if get_boolean_input(f"Whether the faceZone \"{standalone_surfaces[ii]}\" enclose a cellZone? "):
                    cell_zone_name = input("Enter name of the cellZone? ")
                    execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{standalone_surfaces[ii]}/cellZone -add {cell_zone_name}")
                    execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{standalone_surfaces[ii]}/cellZoneInside -add inside")
                layer_surfaces.append(standalone_surfaces[ii])
                layer_surfaces.append(standalone_surfaces[ii]+"_slave")     # For layer addition, both sides of a faceZone has to be put into the patch list
    
       
    execute_command("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/resolveFeatureAngle -add 30")
    
    print("\nEnter the number of cells between mesh levels...")
    print("1 - fast transition, low cell count, may cause convergence issues")
    print("2 - balanced transition and cell count (preferred)")
    print("3 - slow transition, high cell count, robust")
    num_cells_between_levels = int(input("Value = "))

    execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/nCellsBetweenLevels -add {num_cells_between_levels}")

    # castellatedMeshControls --> features section
    
    location_in_mesh = get_vector("\nEnter a point to select the mesh region to be retained (as x y z): ")
    execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/locationInMesh -add \"{location_in_mesh}\"")
    
    execute_command(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/allowFreeStandingZoneFaces -add true")

    #--------------------------------
    # snapControls section
    #--------------------------------
    execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/nSmoothPatch -add 3")
    execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/nSmoothInternal -add 5")
    execute_command(f"foamDictionary system/snappyHexMeshDict -entry snapControls/tolerance -add 2.0")
    execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/nSolveIter -add 30")
    execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/nRelaxIter -add 5")
    execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/nFeatureSnapIter -add 10")

    feature_snap_type = int(input("\nType of snapping feature edges: explicit (1) or implicit (0) ? "))

    if(feature_snap_type == 1):
        if(len(edge_files) > 0):
            execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/implicitFeatureSnap -add false")
            execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/explicitFeatureSnap -add true")
            execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/multiRegionFeatureSnap -add true")
        else:
            print("WARNING: Explicit feature edge snapping chosen, but no feature edges are defined. Continuing with implicit feature edge snapping")
            feature_snap_type = 0
            
    if(feature_snap_type == 0):
        execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/implicitFeatureSnap -add true")
        execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/explicitFeatureSnap -add false")
        execute_command("foamDictionary system/snappyHexMeshDict -entry snapControls/multiRegionFeatureSnap -add false")
    
    #-------------------------------------------
    # Layer addition
    #-----------------------------------------
    if get_boolean_input("\nAdd boundary layers?"):
        print("\n===========================================")
        print("Boundary layer settings")
        print("===========================================")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayers -set true")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/relativeSizes -add true")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/minThickness -add 0.1")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/featureAngle -add 120")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/nGrow -add 0")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/maxFaceThicknessRatio -add 0.5")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/nBufferCellsNoExtrude -add 0")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/nLayerIter -add 50")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/nSmoothThickness -add 10")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/nRelaxIter -add 5")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/nRelaxedIter -add 20")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/nSmoothSurfaceNormals -add 1")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/thicknessModel -add finalAndExpansion")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/finalLayerThickness -add 0.5")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/expansionRatio -add 1.1")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/layers -add \"{}\"")
        
        print("The boundaries/faceZones available for prism layer addition are")
        print(layer_surfaces)

        patch_list = "( "
        for ii in range(len(layer_surfaces)):
            if get_boolean_input(f"\nAdd boundary layers normal to the patch \"{layer_surfaces[ii]}\" ?"):
                patch_list = patch_list + layer_surfaces[ii] + " "
                num_layers = int(input("Enter number of boundary layers for this patch? "))
                execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/layers/"+layer_surfaces[ii]+" -add \"{}\"")
                execute_command(f"foamDictionary system/snappyHexMeshDict -entry addLayersControls/layers/{layer_surfaces[ii]}/nSurfaceLayers -add {num_layers}")
            else:
                print(f"Skipping boundary layers generation for patch \"{layer_surfaces[ii]}\"")
        patch_list = patch_list + ");"

        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/meshShrinker -add displacementMotionSolver")
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/solver -add displacementLaplacian")
        text_string = "{ diffusivity quadratic inverseDistance "+ patch_list +" }"
        execute_command("foamDictionary system/snappyHexMeshDict -entry addLayersControls/displacementLaplacianCoeffs"+" -add \""+text_string+"\"")
        
        # write fvSchemes and fvSolution files necessary for layer addition
        content = """\
FoamFile
{
    version         2;
    format          ascii;
    class           dictionary;
    object          fvSchemes;
}

divSchemes
{

}

gradSchemes
{
    grad(cellDisplacement)  cellLimited leastSquares 1;

}

laplacianSchemes
{
    laplacian(diffusivity,cellDisplacement) Gauss linear limited corrected 0.5;
}

"""
        write_file(system_folder, "fvSchemes", content)
    
        content = """\
FoamFile
{
    format      ascii;
    class       dictionary;
    object      fvSolution;
}

solvers
{
   cellDisplacement
   {
       solver          GAMG;
       smoother        GaussSeidel;
       minIter         1;
       tolerance       1e-7;
       relTol          0.01;
   }
}

"""
        write_file(system_folder, "fvSolution", content)
        
        
    #--------------------------------
    # meshQualityControls section
    #--------------------------------
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/maxNonOrtho -add 65")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/maxBoundarySkewness -add 20")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/maxInternalSkewness -add 4")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/maxConcave -add 80")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minFlatness -add 0.5")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minVol -add 1e-13")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minTetQuality -add -1e-30")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minArea -add -1")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minTwist -add 0.02")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minDeterminant -add 0.001")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minFaceWeight -add 0.05")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minVolRatio -add 0.01")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minTriangleTwist -add -1")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/minEdgeLength -add -1")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/relaxed -add \"{}\"")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/relaxed/maxNonOrtho -add 70")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/nSmoothScale -add 4")
    execute_command("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/errorReduction -add 0.75")

    print(f"File '{snappy_hex_mesh_dict_file}' generation succesfull.")
except FileNotFoundError as e:
    print(e)
except Exception as e:
    print(f"An unexpected error occurred: {e}")
