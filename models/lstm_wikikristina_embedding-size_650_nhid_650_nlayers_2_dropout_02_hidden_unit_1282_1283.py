
import sys
import os

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root not in sys.path:
    sys.path.append(root)

import warnings
warnings.simplefilter(action='ignore')

import torch
import os
import pandas as pd
import numpy as np

from utilities.settings import Params, Paths
from utilities.utils import check_folder, shift


def load():
    from .LSTM import model, utils
    # mod is only used for name retrieving ! the actual trained model is retrieved in the last line
    mod = model.RNNModel('LSTM', 50001, 650, 650, 2, dropout=0.2) # ntoken is chosen randomly, it will or has been determined during training
    data_name = 'wiki_kristina'
    language = 'english'
    return utils.load(mod, data_name, language)
                
def generate(model, run, language, textgrid, overwrite=False):
    from LSTM import model
    from data import Corpus
    name = os.path.basename(os.path.splitext(run)[0])
    run_name = name.split('_')[-1] # extract the name of the run
    save_all = None
    model.param = {'rnn_type':'LSTM', 'ntoken':50001, 'ninp':650, 'nhid':650, 'nlayers':2, 'dropout':0.2, 'tie_weights':False}
    corpus = Corpus(os.path.join(paths.path2data, 'text', 'english', 'lstm_training'), language)
    model.vocab = corpus.dictionary
    model_name = 'lstm_wikikristina_embedding-size_{}_nhid_{}_nlayers_{}_dropout_{}'.format(model.param['ninp'], model.param['nhid'], model.param['nlayers'], str(model.param['dropout']).replace('.', ''))
    check_folder(os.path.join(Paths().path2derivatives, 'fMRI/raw-features', language, model_name))
    path = os.path.join(Paths().path2derivatives, 'fMRI/raw-features', language, model_name, 'raw-features_{}_{}_{}.csv'.format(language, model_name, run_name))

    #### generating raw-features ####
    if (os.path.exists(path)):
        raw_features = pd.read_csv(path)
    else:
        raw_features = model.generate(run, language)
        save_all = path
    #### Retrieving data of interest ####
    columns2retrieve = ['raw-hidden-1282', 'raw-hidden-1283']
    return raw_features[:textgrid.offsets.count()], columns2retrieve, save_all
                

if __name__ == '__main__':
    from LSTM import model, train
    params = Params()
    paths = Paths()
    mod = model.RNNModel('LSTM', 50001, 650, 650, 2, dropout=0.2)
    data = os.path.join(paths.path2data, 'text', 'english', 'lstm_training')
    data_name = 'wiki_kristina'
    language = 'english'
    train.train(mod, data, data_name, language, eval_batch_size=params.pref.eval_batch_size, bsz=params.pref.bsz)
                