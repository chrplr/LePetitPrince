from nilearn.input_data import MultiNiftiMasker
from nilearn.plotting import plot_glass_brain
from sklearn.model_selection import LeaveOneOut, LeaveOneGroupOut
from nilearn.masking import compute_epi_mask
from nilearn.image import math_img, mean_img
import nibabel as nib
from .splitter import Splitter
import sklearn
import numpy as np
import pandas as pd
from tqdm import tqdm
from .utils import get_r2_score, log
from .settings import Params, Paths
import os
import pickle
from os.path import join

import warnings
warnings.simplefilter(action='ignore')


params = Params()
paths = Paths()

#########################################
################ Figures ################
#########################################

def create_maps(masker, distribution, distribution_name, subject, output_parent_folder, vmax=0.2):
    model = os.path.basename(output_parent_folder)
    language = os.path.basename(os.path.dirname(output_parent_folder))
    data_type = os.path.basename(os.path.dirname(os.path.dirname(output_parent_folder)))

    img = masker.inverse_transform(distribution)
    
    path2output_raw = join(output_parent_folder, "{0}_{1}_{2}_{3}_{4}".format(data_type, language, model, distribution_name, subject)+'.nii.gz')
    path2output_png = join(output_parent_folder, "{0}_{1}_{2}_{3}_{4}".format(data_type, language, model, distribution_name, subject)+'.png')

    nib.save(img, path2output_raw)

    display = plot_glass_brain(img, display_mode='lzry', threshold=0, colorbar=True, black_bg=True, vmin=0., vmax=vmax)
    display.savefig(path2output_png)
    display.close()



#########################################
######### First level analysis ##########
#########################################


def compute_global_masker(files): # [[path, path2], [path3, path4]]
    # return a MultiNiftiMasker object

    #spm_dir = '/neurospin/unicog/protocols/IRMf/Meyniel_MarkovGuess_2014'
    #mask = join(spm_dir, 'spm12/tpm/mask_ICV.nii')
    #global_mask = math_img('img>0', img=mask)
    #masker = MultiNiftiMasker(mask_img=global_mask)
    #masker.fit()

    masks = [compute_epi_mask(f) for f in files]
    global_mask = math_img('img>0.5', img=mean_img(masks)) # take the average mask and threshold at 0.5
    masker = MultiNiftiMasker(global_mask, detrend=params.pref.detrend, standardize=params.pref.standardize) # return a object that transforms a 4D barin into a 2D matrix of voxel-time and can do the reverse action
    masker.fit()
    return masker


def do_single_subject(subject, fmri_filenames, design_matrices, masker, output_parent_folder, model, voxel_wised=False, alpha_list=np.logspace(-3, -1, 30)):
    # Compute r2 maps for all subject for a given model
    #   - subject : e.g. : 'sub-060'
    #   - fmri_runs: list of fMRI data runs (1 for each run)
    #   - matrices: list of design matrices (1 for each run)
    #   - masker: MultiNiftiMasker object
    fmri_runs = [masker.transform(f) for f in fmri_filenames] # return a list of 2D matrices with the values of the voxels in the mask: 1 voxel per column
    
    # compute r2 maps and save them under .nii.gz and .png formats
    if voxel_wised:
        alphas, r2_test = per_voxel_analysis(model, fmri_runs, design_matrices, subject, alpha_list)
        create_maps(masker, alphas, 'alphas', subject, output_parent_folder, vmax=5e3) # alphas
    else:
        r2_test = whole_brain_analysis(model, fmri_runs, design_matrices, subject)
    create_maps(masker, r2_test, 'r2_test', subject, output_parent_folder, vmax=0.2) # r2 test


def whole_brain_analysis(model, fmri_runs, design_matrices, subject):
    #   - fmri_runs: list of fMRI data runs (1 for each run)
    #   - matrices: list of design matrices (1 for each run)
    scores = None  # array to contain the r2 values (1 row per fold, 1 column per voxel)
    nb_runs = len(fmri_runs)

    logo = LeaveOneGroupOut() # leave on run out !
    for train, test in tqdm(logo.split(fmri_runs, groups=range(1, nb_runs+1))):
        fmri_data_train = np.vstack([fmri_runs[i] for i in train]) # fmri_runs liste 2D colonne = voxels et chaque row = un t_i
        predictors_train = np.vstack([design_matrices[i] for i in train])

        if type(model) == sklearn.linear_model.RidgeCV:
            nb_samples = np.cumsum([0] + [[fmri_runs[i] for i in train][i].shape[0] for i in range(len([fmri_runs[i] for i in train]))]) # list of cumulative lenght
            indexes = {'run{}'.format(run+1): [nb_samples[i], nb_samples[i+1]] for i, run in enumerate(train)}
            model.cv = Splitter(indexes_dict=indexes, n_splits=nb_runs-1) # adequate splitter for cross-validate alpha taking into account groups
        print('Fitting model...')
        model_fitted = model.fit(predictors_train, fmri_data_train)
        # pickle.dump(model_fitted, open(join(paths.path2derivatives, 'fMRI/glm-indiv/english', str(model).split('(')[0] + '{}.sav'.format(test[0])), 'wb'))
        print('Model fitted.')

        # return the R2_score for each voxel (=list)
        r2 = get_r2_score(model_fitted, fmri_runs[test[0]], design_matrices[test[0]])
        print(r2)

        # log the results
        log(subject, voxel='whole brain', alpha=None, r2=r2)

        scores = r2 if scores is None else np.vstack([scores, r2])
    # result = pd.DataFrame(scores, columns=['voxel #{}'.format(i) for i in range(scores.shape[1])])
    # result.to_csv(join(paths.path2derivatives, 'fMRI/glm-indiv/english', str(model).split('(')[0] + '.csv'))
    return np.mean(scores, axis=0) # compute mean vertically (in time)


def per_voxel_analysis(model, fmri_runs, design_matrices, subject, alpha_list):
    # compute alphas and test score with cross validation
    #   - fmri_runs: list of fMRI data runs (1 for each run)
    #   - design_matrices: list of design matrices (1 for each run)
    #   - nb_voxels: number of voxels
    #   - indexes: dict specifying row indexes for each run
    nb_voxels = fmri_runs[0].shape[1]
    nb_alphas = len(alpha_list)
    nb_runs_test = len(fmri_runs)
    nb_runs_valid = nb_runs_test -1 
    alphas_cv2 = np.zeros((nb_runs_test, nb_voxels))
    scores_cv2 = np.zeros((nb_runs_test, nb_voxels))
    
    # loop for r2 computation
    cv3 = 0
    logo = LeaveOneOut() # leave on run out !
    for train_, test in logo.split(fmri_runs):
        fmri_data_train_ = [fmri_runs[i] for i in train_] # fmri_runs liste 2D colonne = voxels et chaque row = un t_i
        predictors_train_ = [design_matrices[i] for i in train_]
        
        cv2 = 0
        logo2 = LeaveOneOut() # leave on run out !
        for train, valid in logo2.split(fmri_data_train_):
            fmri_data_train = [fmri_data_train_[i] for i in train] # fmri_runs liste 2D colonne = voxels et chaque row = un t_i
            predictors_train = [predictors_train_[i] for i in train]
            dm = np.vstack(predictors_train)
            fmri = np.vstack(fmri_data_train)
            scores_cv1 = np.zeros((nb_voxels, nb_runs_valid, nb_alphas))
            
            cv1 = 0
            for alpha_tmp in tqdm(alpha_list): # compute the r2 for a given alpha for all the voxel
                model.set_params(alpha=alpha_tmp)
                model_fitted = model.fit(dm,fmri)
                r2 = get_r2_score(model_fitted, fmri_data_train_[valid[0]], predictors_train_[valid[0]])
                scores_cv1[:, cv2, cv1] = r2
                cv1 += 1
            #best_alphas_indexes = np.argmax(scores_cv1, axis=1)
            cv2 += 1
        best_alphas_indexes = np.argmax(np.mean(scores_cv1, axis=1), axis=1)
        alphas_cv2[cv3, :] = np.array([alpha_list[i] for i in best_alphas_indexes])
        fmri2 = np.vstack(fmri_data_train_)
        dm2 = np.vstack(predictors_train_)
        for voxel in tqdm(range(nb_voxels)): # loop through the voxels and fit the model with the best alpha for this voxel
            y = fmri2[:,voxel].reshape((fmri2.shape[0],1))
            model.set_params(alpha=alphas_cv2[cv3, voxel])
            model_fitted = model.fit(dm2, y)
            scores_cv2[cv3, voxel] = get_r2_score(model_fitted, 
                                            fmri_runs[test[0]][:,voxel].reshape((fmri_runs[test[0]].shape[0],1)), 
                                            design_matrices[test[0]])
            # log the results
            log(subject, voxel=voxel, alpha=alphas_cv2[cv3, voxel], r2=scores_cv2[cv3, voxel])
        cv3 += 1
        
    return np.mean(alphas_cv2, axis=0), np.mean(scores_cv2, axis=0) # compute mean vertically (in time)
    
    
    
    
    
    
    
    
    
    
