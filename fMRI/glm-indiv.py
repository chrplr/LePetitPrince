############################################
# First level analysis 
# --> R2 maps for GLM models
#
############################################

import sys
import os

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.append(root)

import argparse
from os.path import join
import os.path as op

import warnings
warnings.simplefilter(action='ignore' )

from utilities.settings import Paths, Subjects
from utilities.utils import get_data, get_output_parent_folder, check_folder, transform_design_matrices
from utilities.first_level_analysis import compute_global_masker, do_single_subject
import pandas as pd
import numpy as np
from nilearn.input_data import MultiNiftiMasker

from sklearn.metrics import r2_score
from sklearn.linear_model import LinearRegression
from joblib import Parallel, delayed

paths = Paths()
subjects_list = Subjects()


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="""Objective:\nGenerate r2 maps from design matrices and fMRI data in a given language for a given model.\n\nInput:\nLanguage and models.""")
    parser.add_argument("--subjects", nargs='+', action='append', default=[], help="Subjects list on whom we are running a test: list of 'sub-002...")
    parser.add_argument("--language", type=str, default='en', help="Language of the model.")
    parser.add_argument("--model_name", type=str, help="Name of the model to use to generate the raw features.")
    parser.add_argument("--overwrite", default=False, action='store_true', help="Precise if we overwrite existing files")
    parser.add_argument("--parallel", default=True, action='store_true', help="Precise if we run the code in parallel")

    args = parser.parse_args()
    source = 'fMRI'
    input_data_type = 'design-matrices'
    output_data_type = 'glm-indiv'
    model = LinearRegression()
    model_name = args.model_name
    subjects = args.subjects[0]

    dm = get_data(args.language, input_data_type, model=model_name, source='fMRI')
    fmri_runs = {subject: get_data(args.language, data_type=source, subject=subject) for subject in subjects}

    output_parent_folder = get_output_parent_folder(source, output_data_type, args.language, model_name)
    check_folder(output_parent_folder) # check if the output_parent_folder exists and create it if not

    matrices = [transform_design_matrices(run) for run in dm] # list of design matrices (dataframes) where we added a constant column equal to 1
    masker = compute_global_masker(list(fmri_runs.values()))  # return a MultiNiftiMasker object ... computation is sloow

    if args.parallel:
            Parallel(n_jobs=-1)(delayed(do_single_subject)(sub, fmri_runs[sub], matrices, masker, output_parent_folder, model) for sub in subjects)
    else:
        for sub in subjects:
            print('Processing subject {}...'.format(sub))
            do_single_subject(sub, fmri_runs[sub], matrices, masker, output_parent_folder, model)