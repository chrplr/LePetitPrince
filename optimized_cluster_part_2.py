# -*- coding: utf-8 -*-
########################
# python cluster.py --login ap259944 --password XxxxX --fmri_data /home/ap259944/inputs/fmri_data/ --design_matrices /home/ap259944/inputs/design_matrices/ --model_name lstm_wikikristina_embedding-size_600_nhid_600_nlayers_1_dropout_02_hidden_first-layer --subject sub-057
########################

from soma_workflow.client import Job, Workflow, Helper, Group, WorkflowController
import os
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from nilearn.masking import compute_epi_mask # cause warning
from nilearn.image import math_img, mean_img
from nilearn.input_data import MultiNiftiMasker
from sklearn.model_selection import LeaveOneOut
from nilearn.plotting import plot_glass_brain
import nibabel as nib
import yaml
import glob
import matplotlib.pyplot as plt
plt.switch_backend('agg')
import argparse



############################
### Functions definition ###
############################

def check_folder(path):
    # Create adequate folders if necessary
    try:
        if not os.path.isdir(path):
            check_folder(os.path.dirname(path))
            os.mkdir(path)
    except:
        pass



if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="""Objective:\nUse cluster nodes to perform the Ridge analysis.""")
    parser.add_argument("--login", type=str, default=None, help="Login to connect to the cluster.")
    parser.add_argument("--password", type=str, default=None, help="Password to connect to the cluster.")
    parser.add_argument("--model_name", type=str, default='', help="Name of the model.")
    parser.add_argument("--subject", type=str, default='sub-057', help="Subject name.")

    args = parser.parse_args()


    ###################
    ### Credentials ###
    ###################

    login = args.login 
    password = args.password 


    ######################
    ### Data retrieval ###
    ######################

    inputs_path = "/neurospin/unicog/protocols/IRMf/LePetitPrince_Pallier_2018/LePetitPrince/" # "/Users/alexpsq/Code/NeuroSpin/LePetitPrince/"
    scripts_path = os.path.join(inputs_path, "code/utilities")
    fmri_path = os.path.join(inputs_path, "data/fMRI/english/{}/func/".format(args.subject) )
    design_matrices_path = os.path.join(inputs_path, "derivatives/fMRI/design-matrices/english/{}/".format(args.model_name))
    derivatives_path = os.path.join(inputs_path, "derivatives/fMRI/ridge-indiv/english/{}/{}/".format(args.subject, args.model_name))
    subject_path = os.path.join(inputs_path, "derivatives/fMRI/ridge-indiv/english/{}/".format(args.subject))
    shuffling_path = os.path.join(inputs_path, "derivatives/fMRI/ridge-indiv/english/{}/{}/shuffling.npy".format(args.subject, args.model_name))
    r2_path = os.path.join(inputs_path, "derivatives/fMRI/ridge-indiv/english/{}/{}/r2/".format(args.subject, args.model_name))
    pearson_corr_path = os.path.join(inputs_path, "derivatives/fMRI/ridge-indiv/english/{}/{}/pearson_corr/".format(args.subject, args.model_name))
    distribution_r2_path = os.path.join(inputs_path, "derivatives/fMRI/ridge-indiv/english/{}/{}/distribution_r2/".format(args.subject, args.model_name))
    distribution_pearson_corr_path = os.path.join(inputs_path, "derivatives/fMRI/ridge-indiv/english/{}/{}/distribution_pearson_corr/".format(args.subject, args.model_name))
    yaml_files_path = os.path.join(inputs_path, "derivatives/fMRI/ridge-indiv/english/{}/{}/yaml_files/".format(args.subject, args.model_name))
    output_path = os.path.join(inputs_path, "derivatives/fMRI/ridge-indiv/english/{}/{}/outputs/".format(args.subject, args.model_name))
    log_error_path = "/home/{}/soma-workflow/logs/error_log.txt".format(login)
    log_output_path = "/home/{}/soma-workflow/logs/output_log.txt".format(login)

    #x = sorted(glob.glob(os.path.join(design_matrices_path, 'x_run*')))
    #y = sorted(glob.glob(os.path.join(fmri_path, 'y_run*')))


    ####################
    ### Sanity check ###
    ####################

    all_paths = [inputs_path, 
                    scripts_path,
                    fmri_path, 
                    design_matrices_path, 
                    derivatives_path, 
                    r2_path, 
                    pearson_corr_path,
                    distribution_r2_path, 
                    distribution_pearson_corr_path, 
                    yaml_files_path, 
                    output_path,
                    subject_path,
                    os.path.dirname(log_error_path),
                    os.path.dirname(log_output_path)]
    for path in all_paths:
        check_folder(path)


    ##################
    ### Parameters ###
    ##################

    parameters_path = os.path.join(derivatives_path, 'parameters.yml')

    with open(parameters_path, 'r') as stream:
        try:
            parameters = yaml.safe_load(stream)
        except :
            print(-1)
            quit()
    
    nb_runs = str(parameters['nb_runs'])
    nb_voxels = str(parameters['nb_voxels'])
    nb_features = str(parameters['nb_features'])
    nb_permutations = str(parameters['nb_permutations'])
    alphas = str(parameters['alphas'])
    alpha_percentile = str(parameters['alpha_percentile'])


    ################
    ### Pipeline ###
    ################

    ### Create the workflow:
    dependencies = []
    jobs = []

    # Plotting the maps
    job_final = Job(command=["python", "create_maps.py", 
                                "--input", derivatives_path, 
                                "--parameters", parameters_path,
                                "--subject", args.subject,
                                "--fmri_data", fmri_path], 
                        name="Creating the maps.",
                        working_directory=scripts_path)

    # significativity retrieval 
    files_list = sorted(glob.glob(os.path.join(yaml_files_path, 'run_*_alpha_*.yml')))
    group_significativity = []
    group_score = []
    group_merge =[]
    base_group = []
    count = 1

    for model in parameters['models']:
        model_name = model['name']
        # temporary buffers:
        jobs_score = []
        jobs_perm = []

        # Merging the results and compute significant r2
        job_merge = Job(command=["python", "optimized_merge_results.py", 
                                    "--input_folder", derivatives_path, 
                                    "--yaml_files", yaml_files_path,
                                    "--nb_runs", nb_runs, 
                                    "--nb_voxels", nb_voxels,
                                    "--n_permutations", nb_permutations, 
                                    "--model_name", model_name, 
                                    "--alpha_percentile", alpha_percentile], 
                        name="Merging results for model: {}.".format(model_name),
                        working_directory=scripts_path)

        for yaml_file in files_list:
            info = os.path.basename(yaml_file).split('_')
            run = int(info[1])
            alpha = float(info[3][:-4])
            native_specification = "-q Nspin_bigM  -l walltime=24:00:00" # 
            features_indexes = ','.join([str(index) for index in model['indexes']])
            with open(yaml_file, 'r') as stream:
                try:
                    data = yaml.safe_load(stream)
                except :
                    print(-1)
                    quit()
            if data['voxels']!=[]:
                job = Job(command=["python", "optimized_significance_clusterized.py", 
                                    "--yaml_file", os.path.join(yaml_files_path, yaml_file), 
                                    "--output", derivatives_path, 
                                    "--x", design_matrices_path, 
                                    "--y", fmri_path, 
                                    "--features_indexes", features_indexes,
                                    "--model_name", model_name], 
                            name="job {} - alpha {} - model {}".format(run, alpha, model_name), 
                            working_directory=scripts_path,
                            native_specification=native_specification)
                jobs_score.append(job)
                if count == 1:
                    base_group.append(job)
                job_permutations = Job(command=["python", "optimized_generate_distribution.py", 
                                                "--yaml_file", os.path.join(yaml_files_path, yaml_file), 
                                                "--output", derivatives_path, 
                                                "--x", design_matrices_path, 
                                                "--y", fmri_path, 
                                                "--shuffling", shuffling_path, 
                                                "--n_sample", nb_permutations, 
                                                "--model_name", model_name, 
                                                "--features_indexes", features_indexes], 
                                        name="distribution {} - alpha {} - model {} ".format(run, alpha, model_name), 
                                        working_directory=scripts_path,
                                        native_specification=native_specification)
                jobs_perm.append(job_permutations)
                dependencies.append((job, job_permutations))
                dependencies.append((job_permutations, job_merge))

        group_score += jobs_score
        group_significativity += jobs_perm
        group_merge.append(job_merge)

        if count != 1:
            relationships = zip(base_group, jobs_score)
            for relation  in relationships:
                dependencies.append(relation)

        dependencies.append((job_merge, job_final))
        count -= 1
    
    jobs += group_score + group_significativity + group_merge
    jobs.append(job_final)

    scores = Group(elements=group_score,
                        name="group where test scores are calculated")

    significativity = Group(elements=group_significativity,
                        name="group where distributions are calculated for significance")

    merge = Group(elements=group_merge,
                        name="group where we merge results")

    workflow = Workflow(jobs=jobs,
                        dependencies=dependencies,
                        root_group=[scores, significativity, merge, job_final])
                

    Helper.serialize(os.path.join(inputs_path, 'optimized_cluster_part_2.somawf'), workflow)


    ### Submit the workflow to computing resource (configured in the client-server mode)

    controller = WorkflowController("DSV_cluster_{}".format(login), login, password) #"DSV_cluster_ap259944", login, password

    workflow_id = controller.submit_workflow(workflow=workflow,
                                            name="Cluster optimized part 2")

    
    print("Finished !!!")
