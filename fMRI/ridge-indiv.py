############################################
# First level analysis 
# --> R2 maps for GLM models
#
############################################


import argparse
from os.path import join
import os.path as op

import warnings
warnings.simplefilter(action='ignore' )

from ..utilities.settings import Paths, Subjects
from ..utilities.utils import *
from ..utilities.splitter import Splitter
import pandas as pd
from nilearn.masking import compute_epi_mask
import numpy as np
from nilearn.input_data import MultiNiftiMasker

from sklearn.metrics import r2_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.linear_model import RidgeCV
from nilearn.image import math_img, mean_img
from joblib import Parallel, delayed

paths = Paths()
subjects_list = Subjects()



def per_voxel_analysis(model, fmri_runs, design_matrices, subject):
    # compute alphas and test score with cross validation
    #   - fmri_runs: list of fMRI data runs (1 for each run)
    #   - design_matrices: list of design matrices (1 for each run)
    #   - nb_voxels: number of voxels
    #   - indexes: dict specifying row indexes for each run
    alphas = np.zeros(nb_voxels)
    scores = np.zeros((nb_voxels, nb_runs))
    nb_voxels = fmri_runs[0].shape[1]
    nb_runs = len(fmri_runs)
    count = 0

    logo = LeaveOneGroupOut() # leave on run out !
    for train, test in logo.split(fmri_runs, groups=range(nb_runs)): # loop for r2 computation

        fmri_data_train = [fmri_runs[i] for i in train] # fmri_runs liste 2D colonne = voxels et chaque row = un t_i
        predictors_train = [design_matrices[i] for i in train]
        nb_samples = np.cumsum([0] + [fmri_data_train[i].shape[0] for i in range(len(fmri_data_train))]) # list of cumulative lenght
        indexes = {'run{}'.format(run+1): [nb_samples[i], nb_samples[i+1]] for i, run in enumerate(train)}

        model.cv = Splitter(indexes=indexes, n_splits=nb_runs)
        dm = np.vstack(predictors_train)
        fmri = np.vstack(fmri_data_train)

        for voxel in range(nb_voxels):
            X = dm[:,voxel].reshape((dm.shape[0],1))
            y = fmri[:,voxel].reshape((fmri.shape[0],1))
            # fit the model for a given voxel
            model_fitted = model.fit(X,y)
            # retrieve the best alpha and compute the r2 score for this voxel
            alphas[voxel] = model.alpha_
            scores[voxel, count] = get_r2_score(model_fitted, 
                                                fmri_runs[test[0]][:,voxel].reshape((fmri_runs[test[0]].shape[0],1)), 
                                                design_matrices[test[0]][:,voxel].reshape((design_matrices[test[0]].shape[0],1)))
            # log the results
            log(subject, voxel=voxel, alpha=model_fitted.alpha_, r2=r2_test)
        count += 1
        
    return alphas, np.mean(scores, axis=0) # compute mean vertically (in time)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="""Objective:\nGenerate r2 maps from design matrices and fMRI data in a given language for a given model.\n\nInput:\nLanguage and models.""")
    parser.add_argument("--test", type=bool, default=False, action='store_true', help="Precise if we are running a test.")
    parser.add_argument("--language", type=str, default='en', help="Language of the model.")
    parser.add_argument("--model_name", type=str, help="Name of the model to use to generate the raw features.")
    parser.add_argument("--overwrite", type=bool, default=False, action='store_true', help="Precise if we overwrite existing files")
    parser.add_argument("--parallel", type=bool, default=True, help="Precise if we run the code in parallel")
    parser.add_argument("--voxel_wised", type=bool, default=False, action='store_true', help="Precise if we compute voxel-wised")

    args = parser.parse_args()
    source = 'fMRI'
    input_data_type = 'design-matrices'
    output_data_type = 'ridge-indiv'
    alphas = np.logspace(-3, -1, 30)
    model = RidgeCV(alphas=alphas, scoring='r2', cv=Splitter())
    model_name = args.model_name

    subjects = subjects_list.get_all(args.language, args.test)
    dm = get_data(args.language, input_data_type, model=model_name, source='fMRI', test=args.test)
    fmri_runs = {subject: get_data(args.language, data_type=source, test=args.test, subject=subject) for subject in subjects}

    output_parent_folder = get_output_parent_folder(source, output_data_type, args.language, model_name)
    check_folder(output_parent_folder) # check if the output_parent_folder exists and create it if not

    matrices = [transform_design_matrices(run) for run in dm] # list of design matrices (dataframes) where we added a constant column equal to 1
    masker = compute_global_masker(list(fmri_runs.values()))  # return a MultiNiftiMasker object ... computation is sloow

    if args.parallel:
            Parallel(n_jobs=-1)(delayed(do_single_subject)(sub, fmri_runs[sub], matrices, masker, output_parent_folder, model, ridge=True, voxel_wised=args.voxel_wised) for sub in subjects)
        else:
            for sub in subjects:
                print(f'Processing subject {}...'.format(sub))
                do_single_subject(sub, fmri_runs[sub], matrices, masker, output_parent_folder, model, ridge=True, voxel_wised=args.voxel_wised)
