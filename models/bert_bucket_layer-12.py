import sys
import os

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root not in sys.path:
    sys.path.append(root)

import warnings
warnings.simplefilter(action='ignore')

import os
import pandas as pd


from utilities.settings import Paths
from utilities.utils import check_folder



def load():
    # mod is only used for name retrieving ! the actual trained model is retrieved in the last line
    from .BERT import model
    language = 'english'
    loi = [12]
    name = 'BERT - base - bucket - layers {}'.format(loi)
    #### parameters studied ####
    mod = model.BERT('base', language, name, loi)
    return mod

def generate(mod, run, language, textgrid, overwrite=False):
    name = os.path.basename(os.path.splitext(run)[0])
    run_name = name.split('_')[-1] # extract the name of the run
    save_all = None
    
    # Defining paths
    model_name = 'bert_bucket_all-layers'
    check_folder(os.path.join(Paths().path2derivatives, 'fMRI/raw-features', language, model_name))
    path = os.path.join(Paths().path2derivatives, 'fMRI/raw-features', language, model_name, 'raw-features_{}_{}_{}.csv'.format(language, model_name, run_name))
    #### generating raw-features ####
    if (os.path.exists(path)):
        raw_features = pd.read_csv(path)
    else:
        raw_features = mod.generate(run, language, textgrid)
        save_all = path
    #### Retrieving data of interest ####
    # columns2retrieve = [function.__name__ for function in mod.functions]
    columns2retrieve = ['layer-{}-{}'.format(layer, index) for layer in mod.loi for index in range(mod.FEATURE_COUNT)]
    return raw_features[:textgrid.offsets.count()], columns2retrieve, save_all