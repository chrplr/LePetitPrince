import glob
import os
from os.path import join
from .settings import Paths, Extensions, Params


from tqdm import tqdm
from time import time
import numpy as np
import pandas as pd
import csv
from sklearn.metrics import r2_score
from sklearn.preprocessing import StandardScaler
import plotly.plotly as py

paths = Paths()
extensions = Extensions()
params = Params()


#########################################
############ Data retrieving ############
#########################################

def get_data(language, data_type, subject=None, source='', model=''):
    # General function for data retrieving
    # Output: list of path to the different data files
    extension = extensions.get_extension(data_type)
    sub_dir = os.listdir(paths.path2data)
    if data_type in sub_dir:
        base_path = paths.path2data
        if data_type in ['fMRI', 'MEG']:
            file_pattern = '{2}/func/{0}_{1}_{2}_run*'.format(data_type, language, subject) + extension
        else:
            file_pattern = '{}_{}_{}_run*'.format(data_type, language, model) + extension
    else:
        base_path = join(paths.path2derivatives, source)
        file_pattern = '{}_{}_{}_run*'.format(data_type, language, model) + extension
    data = sorted(glob.glob(join(base_path, '{0}/{1}/{2}'.format(data_type, language, model), file_pattern)))
    return data


def get_output_parent_folder(source, output_data_type, language, model):
    return join(paths.path2derivatives, '{0}/{1}/{2}/{3}'.format(source, output_data_type, language, model))


def get_path2output(output_parent_folder, output_data_type, language, model, run_name, extension):
    return join(output_parent_folder, '{0}_{1}_{2}_{3}'.format(output_data_type, language, model, run_name) + extension)



#########################################
###### Computation functionalities ######
#########################################

def compute(path, overwrite=False):
    # Tell us if we can compute or not
    result = True
    if os.path.isfile(path):
        result = overwrite
    return result


def check_folder(path):
    # Create adequate folders if necessary
    if not os.path.isdir(path):
        os.mkdir(path)



#########################################
################## Log ##################
#########################################

def log(subject, voxel, alpha, r2):
    """ log stats per fold to a csv file """
    logcsvwriter = csv.writer(open("test.log", "a+"))
    if voxel == 'whole brain':
        logcsvwriter.writerow([subject, voxel, np.mean(r2), np.std(r2),
                            np.min(r2), np.max(r2)])
    else:
        logcsvwriter.writerow([subject, voxel, alpha, r2])


#########################################
########## Classical functions ##########
#########################################


def get_r2_score(model, y_true, y2predict, r2_min=0., r2_max=0.99):
    # return the R2_score for each voxel (=list)
    r2 = r2_score(y_true,
                    model.predict(y2predict),
                    multioutput='raw_values')
    # remove values with are too low and values too good to be true (e.g. voxels without variation)
    return np.array([0 if (x < r2_min or x >= r2_max) else x for x in r2])


def transform_design_matrices(path):
    # Read design matrice csv file and add a column with only 1
    dm = pd.read_csv(path, header=0).values
    scaler = StandardScaler(with_mean=params.scaling_mean, with_std=params.scaling_var)
    scaler.fit(dm)
    dm = scaler.transform(dm)
    # add the constant
    const = np.ones((dm.shape[0], 1))
    dm = np.hstack((dm, const))
    return dm 



#########################################
################## PCA ##################
#########################################
# Compute a Dual-STATIS analysis 
# takes account of the similarities between the variance-covariance matrices of the groups


def pca(X, n_components=50):
    """
    See paper:
    General overview of methods of analysis of multi-group datasets
    Aida Eslami, El Mostafa Qannari, Achim Kohler, Stephanie Bougeard
    """
    M = len(X) # number of groups
    # Computing variance-covariance matrix for each group
    cov_matrices = [np.cov(matrix, rowvar=False) for matrix in X]
    R = np.zeros((M, M))
    for i in range(M):
        for k in range(M):
            R[i,k] = np.trace(np.dot(cov_matrices[i], cov_matrices[k]))
    # Computing alphas
    eig_values, eig_vectors = np.linalg.eig(R)
    alphas = eig_vectors[:, np.argmax(eig_values)] # eigen vector associated with the largest eigen value
    # 'Mean' variance-covariance matrix construction
    Vc = np.zeros(cov_matrices[0].shape)
    for index in range(len(cov_matrices)):
        Vc = np.add(Vc, np.dot(alphas[index], cov_matrices[index]))
    # spectral decomposition of Vc
    eig_values_Vc, A = np.linalg.eig(Vc)
    # u,s,v = np.linalg.svd(X_std.T)
    diag_matrix = np.diag(eig_values_Vc)
    ########## testing ##########
    for matrix in cov_matrices:
        for index in range(A.shape[0]):
            print(np.dot(np.dot(A[index], matrix), A[index].T))
    #############################
    eig_pairs = [(np.abs(eig_values_Vc[i]), A[:,i]) for i in range(len(eig_values_Vc))]
    eig_pairs.sort()
    eig_pairs.reverse()
    tot = sum(eig_values_Vc)
    var_exp = [(val / tot)*100 for val in sorted(eig_values_Vc, reverse=True)]
    cum_var_exp = np.cumsum(var_exp)
    ########## check for n_components ##########
    plot(eig_values_Vc, var_exp, cum_var_exp)
    ##################################################
    projected_matrices = []
    projector = eig_pairs[0][1].reshape(-1, 1)
    for index in range(1, n_components):
        projector = np.hstack((projector, eig_pairs[index][1].reshape(-1, 1)))
    for matrix in X:
        projected_matrices.append(np.dot(matrix, projector))
    return projected_matrices



  def plot(eig_values_Vc, var_exp, cum_var_exp):
      trace1 = dict(
        type='bar',
        x=['PC %s' %i for i in range(1,len(eig_values_Vc))],
        y=var_exp,
        name='Individual'
    )
    trace2 = dict(
        type='scatter',
        x=['PC %s' %i for i in range(1,len(eig_values_Vc))], 
        y=cum_var_exp,
        name='Cumulative'
    )
    data = [trace1, trace2]
    layout=dict(
        title='Explained variance by different principal components',
        yaxis=dict(
            title='Explained variance in percent'
        ),
        annotations=list([
            dict(
                x=1.16,
                y=1.05,
                xref='paper',
                yref='paper',
                text='Explained Variance',
                showarrow=False,
            )
        ])
    )
    fig = dict(data=data, layout=layout)
    py.iplot(fig, filename='selecting-principal-components')