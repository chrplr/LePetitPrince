################################################################
# General Language Model including :
#   - an embedding layer
#   - LSTM layers: (nlayers, nhidden)
#
################################################################
import sys
import os

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if root not in sys.path:
    sys.path.append(root)


import torch
import torch.nn as nn
import pandas as pd
import numpy as np
from .data import Corpus, Dictionary
from .tokenizer import tokenize
from utilities.settings import Params
import utils


params = Params()


class RNNModel(nn.Module):
    """Container module with an encoder, a recurrent module, and a decoder."""

    def __init__(self, rnn_type, ntoken, ninp, nhid, nlayers, dropout=0.5, tie_weights=False):
        super(RNNModel, self).__init__()
        self.drop = nn.Dropout(dropout)
        self.encoder = nn.Embedding(ntoken, ninp)
        if rnn_type in ['LSTM', 'GRU']:
            self.rnn = getattr(nn, rnn_type)(ninp, nhid, nlayers, dropout=dropout)
        else:
            try:
                nonlinearity = {'RNN_TANH': 'tanh', 'RNN_RELU': 'relu'}[rnn_type]
            except KeyError:
                raise ValueError( """An invalid option for `--model` was supplied,
                                 options are ['LSTM', 'GRU', 'RNN_TANH' or 'RNN_RELU']""")
            self.rnn = nn.RNN(ninp, nhid, nlayers, nonlinearity=nonlinearity, dropout=dropout)
        self.decoder = nn.Linear(nhid, ntoken)
        # hack the forward function to send an extra argument containing the model parameters
	    # self.rnn.forward = lambda input, hidden: lstm.forward(model.rnn, input, hidden)

        # Optionally tie weights as in:
        # "Using the Output Embedding to Improve Language Models" (Press & Wolf 2016)
        # https://arxiv.org/abs/1608.05859
        # and
        # "Tying Word Vectors and Word Classifiers: A Loss Framework for Language Modeling" (Inan et al. 2016)
        # https://arxiv.org/abs/1611.01462
        if tie_weights:
            if nhid != ninp:
                raise ValueError('When using the tied flag, nhid must be equal to emsize')
            self.decoder.weight = self.encoder.weight

        self.init_weights()

        self.rnn_type = rnn_type
        self.nhid = nhid
        self.ntoken = ntoken
        self.dropout = dropout
        self.ninp = ninp
        self.nlayers = nlayers
        self.backup = self.rnn.forward
        self.vocab = None
    
    def init_vocab(self, path):
        self.vocab = Dictionary(path)

    def __name__(self):
        return '_'.join([self.rnn_type, 'vocab-size', str(self.ntoken), 'embedding-size', str(self.ninp),'nhid', str(self.nhid), 'nlayers', str(self.nlayers), 'dropout', str(self.dropout)])

    def init_weights(self):
        initrange = 0.1
        self.encoder.weight.data.uniform_(-initrange, initrange)
        self.decoder.bias.data.zero_()
        self.decoder.weight.data.uniform_(-initrange, initrange)

    def forward(self, input, hidden):
        emb = self.drop(self.encoder(input))
        output, hidden = self.rnn(emb, hidden)
        output = self.drop(output)
        decoded = self.decoder(output.view(output.size(0)*output.size(1), output.size(2)))
        return decoded.view(output.size(0), output.size(1), decoded.size(1)), hidden

    def init_hidden(self, bsz):
        weight = next(self.parameters())
        if self.rnn_type == 'LSTM':
            return (weight.new_zeros(self.nlayers, bsz, self.nhid),
                    weight.new_zeros(self.nlayers, bsz, self.nhid))
        else:
            return weight.new_zeros(self.nlayers, bsz, self.nhid)

    def generate(self, path, language, includ_surprisal=params.pref.surprisal, parameters=params.pref.extracted_parameters):
        parameters = sorted(parameters)
        # hack the forward function to send an extra argument containing the model parameters
        self.rnn.forward = lambda input, hidden: utils.forward(self.rnn, input, hidden)
        columns_activations = ['raw-{}-{}'.format(name, i) for i in range(self.nhid * self.nlayers) for name in parameters]
        activations = []
        surprisals = []
        iterator = tokenize(path, language, self.vocab)
        last_item = params.eos_separator
        out = None
        hidden = None
        for item in iterator:
            activation, surprisal,(out, hidden) = self.extract_activations(item, last_item=last_item, out=out, hidden=hidden)
            last_item = item
            activations.append(activation)
            surprisals.append(surprisal)
        activations_df = pd.DataFrame(np.vstack(activations), columns=columns_activations)
        surprisals_df = pd.DataFrame(np.vstack(surprisals), columns=['surprisal'])
        result = pd.concat([activations_df, surprisals_df], axis = 1) if includ_surprisal else activations_df
        return result
    
    def extract_activations(self, item, last_item, out=None, hidden=None, parameters=['hidden']):
        activation = []
        if last_item == params.eos_separator:
            hidden = self.init_hidden(1)
            inp = torch.autograd.Variable(torch.LongTensor([[self.vocab.word2idx[params.eos_separator]]]))
            if params.cuda:
                inp = inp.cuda()
            out, hidden = self(inp, hidden)
        surprisal = out[0, 0, self.vocab.word2idx[item]].item()
        inp = torch.autograd.Variable(torch.LongTensor([[self.vocab.word2idx[item]]]))
        if params.cuda:
            inp = inp.cuda()
        out, hidden = self(inp, hidden)
        for param in parameters:
            activation.append(self.rnn.gates[param].data.view(1,1,-1).cpu().numpy()[0][0])
        return np.hstack(activation), surprisal, (out, hidden)
