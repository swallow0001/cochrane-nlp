# coding: utf-8

# # Multitask Learning
# 
# Use a single shared representation to predict gender and phase 2

# ### Load Embeddings and Abstracts

# In[1]:

import os

from collections import OrderedDict

import plac
import pickle

import numpy as np

from sklearn.cross_validation import KFold

import keras

from keras.models import Graph, model_from_json
from keras.layers.core import Dense, Dropout, Activation, Flatten
from keras.layers.embeddings import Embedding
from keras.layers.convolutional import Convolution1D, MaxPooling1D
from keras.utils.layer_utils import model_summary

from support import classinfo_generator, produce_labels, ValidationCallback

class Model:
    def load_embeddings(self):
        """Load word embeddings and abstracts
        
        embeddings_info dict
        --------------------
        abstracts: full-text abstracts
        abstracts_padded: abstracts indexed and padded
        embeddings: embedding matrix
        word_dim: dimension word embeddings
        word2idx: dictionary from word to embedding index
        idx2word: dictionary from embedding index to word
        maxlen: size of each padded abstract
        vocab_size: number of words in the vocabulary
            
        """
        embeddings_info = pickle.load(open('embeddings_info.p', 'rb'))

        self.abstracts = embeddings_info['abstracts']
        self.abstracts_padded = embeddings_info['abstracts_padded']
        self.embeddings = embeddings_info['embeddings']
        self.word_dim = embeddings_info['word_dim']
        self.word2idx, idx2word = embeddings_info['word2idx'], embeddings_info['idx2word']
        self.maxlen = embeddings_info['maxlen']
        self.vocab_size = embeddings_info['vocab_size']

    def load_labels(self, label_names):
        """Load labels for dataset

        Mainly configure class names and validation data

        """
        # Dataframes of labels
        pruned_dataset = pickle.load(open('pruned_dataset.p', 'rb'))
        binarized_dataset = pickle.load(open('binarized_dataset.p', 'rb'))

        # Only consider subset of labels passed in
        pruned_dataset = pruned_dataset[label_names]
        binarized_dataset = binarized_dataset[label_names]

        ys = np.array(binarized_dataset).T # turn labels into numpy array

        # Get class names and sizes
        class_info = list(classinfo_generator(pruned_dataset))
        class_names, self.class_sizes = zip(*class_info)
        class_names = {label: classes for label, classes in zip(label_names, class_names)}

        # Train Test Split
        fold = KFold(len(self.abstracts_padded), n_folds=5, shuffle=True)
        p = iter(fold)
        train_idxs, val_idxs = next(p)
        self.num_train, self.num_val = len(train_idxs), len(val_idxs)

        # Extract training data to pass to keras fit()
        self.train_data = OrderedDict(produce_labels(label_names, self.class_sizes, ys[:, train_idxs]))
        self.train_data.update({'input': self.abstracts_padded[train_idxs]})

        # Extract validation data to validate over
        self.val_data = OrderedDict(produce_labels(label_names, self.class_sizes, ys[:, val_idxs]))
        self.val_data.update({'input': self.abstracts_padded[val_idxs]})

        self.label_names = label_names

    def build_model(self, nb_filter, filter_len, hidden_dim):
        """Build keras model

        Check to see if one already exists on disk. If so, use that one instead.
        
        Current architecture is embedding -> conv -> pool -> fc -> fork.
            
        """
        model = Graph()

        # Input Layer
        model.add_input(name='input',
                        input_shape=[self.maxlen],
                        dtype='int') # dtype='int' is 100% necessary for some reason!

        # Embedding Layer with dropout
        model.add_node(Embedding(input_dim=self.vocab_size, output_dim=self.word_dim,
                                 weights=[self.embeddings],
                                 input_length=self.maxlen,
                                 trainable=False),
                       name='embedding', input='input')
        model.add_node(Dropout(0.25), name='dropout1', input='embedding')

        # Convolution layer
        model.add_node(Convolution1D(nb_filter=nb_filter,
                                     filter_length=filter_len,
                                     activation='relu'),
                       name='conv',
                       input='dropout1')

        # Non-maximum Supression
        model.add_node(MaxPooling1D(pool_length=self.maxlen-1), name='pool', input='conv')

        # Flatten Layer
        model.add_node(Flatten(), name='flat', input='pool')

        # Dense Layer
        model.add_node(Dense(hidden_dim), name='z', input='flat')
        model.add_node(Activation('relu'), name='shared', input='z')
        model.add_node(Dropout(0.25), name='dropout2', input='shared')

        # Fork the graph and predict probabilities for each target from shared representation
        for label, num_classes in zip(self.label_names, self.class_sizes):
            model.add_node(Dense(output_dim=num_classes, activation='softmax'),
                           name='{}_probs'.format(label),
                           input='dropout2')
            model.add_output(name=label, input='{}_probs'.format(label)) # separate output for each label

        model.compile(optimizer='rmsprop',
                    loss={label: 'categorical_crossentropy' for label in self.label_names}) # CE for all the targets

        model_summary(model)

        self.model = model

    def train(self, nb_epoch, batch_size, val_every):
        """Train the model for a fixed number of epochs

        Save the weights after every epoch

        """
        val_callback = ValidationCallback(self.val_data, batch_size, self.num_train, val_every)
        checkpointer = keras.callbacks.ModelCheckpoint(filepath='weights.hd5', verbose=2)

        history = self.model.fit(self.train_data, batch_size=batch_size,
                                 nb_epoch=nb_epoch, verbose=2,
                                 callbacks=[checkpointer, val_callback])


@plac.annotations(
        nb_epoch=('number of epochs', 'option', None, int),
        labels=('labels to predict', 'option'),
        nb_filter=('number of filters', 'option', None, int),
        filter_len=('length of filter', 'option', None, int),
        hidden_dim=('size of hidden state', 'option', None, int),
        batch_size=('batch size', 'option', None, int),
        val_every=('number of times to compute validation per epoch', 'option', None, int)
)
def main(nb_epoch=5, labels='gender,phase_1',
        nb_filter=128, filter_len=2, hidden_dim=128,
        batch_size=128, val_every=2):

    labels = labels.split(',')

    m = Model()

    # Load embeddings and labels
    m.load_embeddings()
    m.load_labels(labels)

    # # Already built a model and it's on disk?
    # if os.path.isfile('model.json'):
    #     m.model = model_from_json(open('model.json').read())
    #     if os.path.isfile('weights.hd5'):
    #         m.model.load_weights('weights.hd5')
    # else:
    m.build_model(nb_filter, filter_len, hidden_dim) # build model from scratch!

    # # Save model to disk
    # json_string = m.model.to_json()
    # open('model.json', 'w').write(json_string)

    m.train(nb_epoch, batch_size, val_every)

if __name__ == '__main__':
    plac.call(main)
