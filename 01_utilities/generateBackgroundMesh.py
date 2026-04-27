#!/usr/bin/env python3
"""
Filename: generateBackgroundMesh.py
Author: G. Vijaya Kumar
Date: December 30, 2023
Description: Generate the background mesh for snappyHexMesh based on a given stl file and the base grid sizes in coordinate directions.
"""

import subprocess
import re
import tempfile
import sys
import os
import argparse
import numpy as np


#---------------------------------------------------------------------------------
# Function to check if the base grid size are positive floating point values
#---------------------------------------------------------------------------------
def positive_float(value):
    try:
        float_value = float(value)
        if float_value > 0:
            return float_value
        else:
            raise argparse.ArgumentTypeError("Value must be greater than 0.")
    except ValueError:
        raise argparse.ArgumentTypeError("Invalid float value.")

#---------------------------------------------------------------------------------
# Function to run the surfaceCheck command of OpenFOAM
#---------------------------------------------------------------------------------
def run_surface_check(stl_filename, output_file):
    # Run the surfaceCheck command and write the output to the specified file
    command = ["surfaceCheck", stl_filename]
    try:
        with open(output_file, 'w') as temp_file:
            result = subprocess.run(command, stdout=temp_file, text=True, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error running surfaceCheck: {e}")
        return None

#---------------------------------------------------------------------------------
# Function to extract the domain extents of the given stl file
#---------------------------------------------------------------------------------
def extract_bounding_box_info(output):
    # Use regular expression to extract bounding box information
    pattern = re.compile(r'Bounding Box : \((-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)\) \((-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)\)')
    match = pattern.search(output)
    if match:
        x1, y1, z1, x2, y2, z2 = map(float, match.groups())
        return x1, y1, z1, x2, y2, z2
    else:
        print("Bounding box information not found in the output.")
        return None

#---------------------------------------------------------------------------------
# Function to create blockMesh dict
    # Scales the bounding box by 1.1 factor
    # Converts the base grid size into number of cells in coordinate directions.
#---------------------------------------------------------------------------------
def create_block_mesh_dict(system_folder, bounding_box_info, dx, dy, dz):
    # Create the "system" folder if it doesn't exist
    os.makedirs(system_folder, exist_ok=True)

    # Define the file path for blockMeshDict
    block_mesh_dict_path = os.path.join(system_folder, 'blockMeshDict')

    # Delete the file if it already exists
    if os.path.exists(block_mesh_dict_path):
        print("A blockMeshDict file already exists in the system folder. Removing it..")
        os.remove(block_mesh_dict_path)

    xMin, yMin, zMin, xMax, yMax, zMax = bounding_box_info
    minCoords = np.array([xMin, yMin, zMin])
    maxCoords = np.array([xMax, yMax, zMax])
    delta = np.array([dx, dy, dz])
    nCells = []
    
    # scaling factor to make the background mesh larger the domain extents of the STL 
    scaleBox = 1.1

    for i in range(3):
        C = 0.5*(minCoords[i]+maxCoords[i])
        minCoords[i] = C - scaleBox*(C - minCoords[i])
        maxCoords[i] = C + scaleBox*(maxCoords[i] - C)

    for i in range(3):
        length = maxCoords[i]-minCoords[i]

        if length <= 0:
            raise ValueError("Error: Length must be a positive number.")

        if length > delta[i]:
            tempNum = int(length/delta[i])
            tempMaxCoords = minCoords[i] + tempNum*delta[i]

            if tempMaxCoords < maxCoords[i]:
                tempNum = tempNum + 1
                maxCoords[i] = minCoords[i] + tempNum*delta[i]
                
            nCells.append(tempNum)
        else:
            raise ValueError("Error: Length of an edge is less than or equal to base grid. Cannot proceed.")
    
    # minCoords and maxCoords may have changed, so update
    xMin, yMin, zMin, xMax, yMax, zMax = minCoords[0], minCoords[1], minCoords[2], maxCoords[0], maxCoords[1], maxCoords[2]

    # Create a new file
    with open(block_mesh_dict_path, 'w') as block_mesh_dict_file:
        # Write content to the file (you can customize this part)
        block_mesh_dict_file.write("/*--------------------------------*- C++ -*----------------------------------*\\\n")
        block_mesh_dict_file.write("| =========                 |                                                 |\n")
        block_mesh_dict_file.write("| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n")
        block_mesh_dict_file.write("|  \\\\    /   O peration     | Version:  v2312                                 |\n")
        block_mesh_dict_file.write("|   \\\\  /    A nd           | Website:  www.openfoam.com                      |\n")
        block_mesh_dict_file.write("|    \\\\/     M anipulation  |                                                 |\n")
        block_mesh_dict_file.write("\\*---------------------------------------------------------------------------*/\n")
        block_mesh_dict_file.write("FoamFile\n")
        block_mesh_dict_file.write("{\n")
        block_mesh_dict_file.write("\tversion     2.0;\n")
        block_mesh_dict_file.write("\tformat      ascii;\n")
        block_mesh_dict_file.write("\tclass       dictionary;\n")
        block_mesh_dict_file.write("\tobject      blockMeshDict;\n")
        block_mesh_dict_file.write("}\n")
        block_mesh_dict_file.write("// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n")
        block_mesh_dict_file.write("\nscale\t1;\n\n")
        block_mesh_dict_file.write("vertices\n")
        block_mesh_dict_file.write("(\n")
        block_mesh_dict_file.write(f"\t({xMin} {yMin} {zMin})\n")
        block_mesh_dict_file.write(f"\t({xMax} {yMin} {zMin})\n")
        block_mesh_dict_file.write(f"\t({xMax} {yMax} {zMin})\n")
        block_mesh_dict_file.write(f"\t({xMin} {yMax} {zMin})\n")
        block_mesh_dict_file.write(f"\t({xMin} {yMin} {zMax})\n")
        block_mesh_dict_file.write(f"\t({xMax} {yMin} {zMax})\n")
        block_mesh_dict_file.write(f"\t({xMax} {yMax} {zMax})\n")
        block_mesh_dict_file.write(f"\t({xMin} {yMax} {zMax})\n")
        block_mesh_dict_file.write(");\n")
        block_mesh_dict_file.write("\nblocks\n")
        block_mesh_dict_file.write("(\n")
        block_mesh_dict_file.write(f"\thex (0 1 2 3 4 5 6 7) ({nCells[0]} {nCells[1]} {nCells[2]}) simpleGrading (1 1 1)\n")
        block_mesh_dict_file.write(");\n\n")
        block_mesh_dict_file.write("// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //")
        
    print(f"blockMeshDict file created at: {block_mesh_dict_path}")

#---------------------------------------------------------------------------------
# Main function
#---------------------------------------------------------------------------------
if __name__ == "__main__":
    #-----------------------------------------------------------------------------------------------
    # Parsing the input arguments: stl file path and the base grid size in coordinate directions
    #-----------------------------------------------------------------------------------------------
    parser = argparse.ArgumentParser(description="Generate the background mesh for snappyHexMesh based on a given stl file and the base grid sizes in coordinate directions. Note: Base grid sizes should be positive values only.")
    parser.add_argument("-stlPath", required=True, help="Path to the STL file.")
    parser.add_argument("-dx", type=positive_float, required=True, help="base grid size in x-direction")
    parser.add_argument("-dy", type=positive_float, required=True, help="base grid size in y-direction")
    parser.add_argument("-dz", type=positive_float, required=True, help="base grid size in z-direction")

    args = parser.parse_args()

    stl_file = args.stlPath

    dx = args.dx
    dy = args.dy
    dz = args.dz

    print("Generating background mesh..")

    # Create the "programOutputs" directory if it doesn't exist
    output_folder = os.path.join(os.getcwd(), 'programOutputs')
    os.makedirs(output_folder, exist_ok=True)
    
    #-----------------------------------------------------------------------------------------------
    # surfaceCheck utility of OpenFOAM is run and from the bounding box of the stl file is extracted
    #-----------------------------------------------------------------------------------------------
        # Create a temporary file in the "programOutputs" directory to store the surfaceCheck output
    temp_filename = os.path.join(output_folder, 'surfaceCheck_blockMesh.log')

    # Step 1: Run surfaceCheck and write the output to the temporary file
    return_code = run_surface_check(stl_file, temp_filename)

    if return_code == 0:
        # Read the contents of the temporary file
        with open(temp_filename, 'r') as temp_file:
            surface_check_output = temp_file.read()

        # Step 2: Extract bounding box information from the output
        bounding_box_info = extract_bounding_box_info(surface_check_output)

        if bounding_box_info is not None:
            # Step 3: Save the bounding box values to variables
            xMin, yMin, zMin, xMax, yMax, zMax = bounding_box_info
    else:
        print(f"Error running surfaceCheck. Return code: {return_code}")

    #-----------------------------------------------------------------------------------------------
    # Creating the blockMeshDict and running blockMesh utility
    #-----------------------------------------------------------------------------------------------
    print("Writing blockMeshDict to system folder.")

    # Check if "system" folder exists in the current directory
    system_folder_path = os.path.join(os.getcwd(), 'system')
    if not os.path.exists(system_folder_path) or not os.path.isdir(system_folder_path):
        raise FileNotFoundError("The 'system' folder does not exist in the current directory.")

    # Create or recreate the blockMeshDict file in the "system" folder
    create_block_mesh_dict(system_folder_path, bounding_box_info, dx, dy, dz)
    
    print("Running OpenFOAM utiltiy \"blockMesh\"..")
    constant_folder_path = os.path.join(os.getcwd(), 'constant', 'polyMesh')

    if os.path.exists(constant_folder_path) and os.path.isdir(constant_folder_path):
        print("The 'polyMesh' folder is present in the 'constant' directory. It will be overwritten.")

    log_file_path = os.path.join(output_folder, 'blockMesh.log')
    try:
        with open(log_file_path, 'w') as log_file:
            subprocess.run(["blockMesh"], stdout=log_file, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running 'blockMesh' command: {e}")

    print("Background mesh generated successfuly.")
