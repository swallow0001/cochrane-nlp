import operator

import matplotlib.pyplot as plt

import numpy as np
import pandas as pd

import keras
from keras.utils.np_utils import to_categorical

import sklearn


class TestCallback(keras.callbacks.Callback):
    def __init__(self):
        super(TestCallback, self).__init__()

    def on_batch_end(self, batch, logs={}):
        print len(self.model.validation_data)
        print self.model.output_order

class ValidationCallback(keras.callbacks.Callback):
    """Callback to compute accuracy during training"""

    def __init__(self, val_data, batch_size, num_train, val_every):
        """Callback to compute accuracy during training
        
        Parameters
        ----------
        val_data : dict containing input and labels
        batch_size : number of examples per batch
        num_train : number of examples in training set
        val_every : number of times to to validation during an epoch

        Also save the validation accuracies when you compute them.
        
        """
        super(ValidationCallback, self).__init__()

        self.val_data = val_data
        self.num_batches_since_val = 0
        num_minis_per_epoch = (num_train/batch_size) # number of minibatches per epoch
        self.K = num_minis_per_epoch / val_every # number of batches to go before doing validation
        
    def on_batch_end(self, batch, logs={}):
        """Do validation if it's been a while
        
        Concretely print out fscores for each class val_every number of times
        per epoch.
        
        """
        # Hasn't been long enough since your last validation run?
        if self.num_batches_since_val < self.K-1:
            self.num_batches_since_val += 1
            return
            
        predictions = self.model.predict(self.val_data)
        
        for label, ys_pred in predictions.items():
            ys_val = self.val_data[label]
            f1 = sklearn.metrics.f1_score(ys_val.argmax(axis=1),
                                          ys_pred.argmax(axis=1), average='macro')

            print '{} f1:'.format(label), f1

        self.num_batches_since_val = 0

def plot_confusion_matrix(confusion_matrix, columns):
    df = pd.DataFrame(confusion_matrix, columns=columns, index=columns)
    axes = plt.gca()
    axes.imshow(df, interpolation='nearest')
    tick_marks = np.arange(len(columns))
    plt.xticks(tick_marks, df.index, rotation=90)
    plt.yticks(tick_marks, df.index)
    plt.ylabel('True label')
    plt.xlabel('Predicted label')

    width = height = len(columns)

    for x in xrange(width):
        for y in xrange(height):
            axes.annotate(str(confusion_matrix[x][y]) if confusion_matrix[x][y] else '', xy=(y, x), 
                        horizontalalignment='center',
                        verticalalignment='center')

def classinfo_generator(df):
    """Generates tuples of class sizes and class names
    
    Parameters
    ----------
    df : dataframe which contains the training labels
    
    """
    for column in df.columns:
        categories = df[column].cat.categories
        yield categories, len(categories)

def produce_labels(label_names, class_sizes, ys):
    """Generates dict of label_names for a minibatch for each objective
    
    Parameters
    ----------
    label_names : list of label names (order must correspond to label_names in ys)
    class_sizes : list of class sizes
    ys : labels
    
    Will produce a dict like:
    
    {gender: 2darray, phase: 2darray, ..., masking: 2darray}
    
    where 2darray has one-hot label_names for every row.
    
    """
    num_objectives, num_train = ys.shape
    
    for label, num_classes, y_row in zip(label_names, class_sizes, ys):        
        ys_block = to_categorical(y_row)

        # Take into account missing label_names!
        missing_data = np.argwhere(y_row == -1).flatten()
        ys_block[missing_data] = 0
        
        yield (label, ys_block)

def examples_generator(dataset, target='gender', num_examples=None):
    """Generate indexes into dataset to pull out examples of classes
    
    Generate n examples for each class where n is the number of examples for the class
    we have the fewest examples for.
    
    """
    labels = dataset[target].unique()
    
    if not num_examples:
        num_class_examples = dataset.groupby('gender').size()
        num_examples = min(num_class_examples) # only get a number of examples such that we have perfect class balance
    
    for label in labels:
        for idx, entry in dataset[dataset[target] == label][:num_examples].iterrows():
            yield idx

    dataset = dataset.loc[list(examples_generator(dataset, num_examples=50))]

    dataset.groupby('gender').size()

#from sklearn.cross_validation import KFold
#
#fold = KFold(len(abstracts_padded), n_folds=5, shuffle=True)
#p = iter(fold)
#
#train_idxs, val_idxs = next(p)
#val_idxs = train_idxs # HARD-CODE VALIDATION SET TO TRAINING SET FOR NOW!!!
#
#X_train, ys_train = abstracts_padded[train_idxs], ys[:, train_idxs]
#X_val, ys_val = abstracts_padded[val_idxs], ys[:, val_idxs]
#
#num_train, num_val = len(X_train), len(X_val)
#
#val_dict = {label: y_row for label, y_row in zip(labels, ys_val)}

#def batch_generator(ys, batch_size, balanced=True):
#    """Yield successive batches for training
#    
#    This generator is not meant to be exhausted, but rather called by next().
#    
#    Each batch has batch_size/num_classes number of examples from each class
#    
#    """
#    num_objectives, num_train = ys.shape
#    
#    while True:
#        yield np.random.choice(num_train, size=batch_size)

#train_batch = batch_generator(ys_train, batch_size)
#
#from support import produce_labels
#
#num_minis_per_epoch = (num_train/batch_size) # number of minibatches per epoch
#num_batches = num_epochs * num_minis_per_epoch # go through n epochs
#
#for i in range(num_batches):
#    if not i % num_minis_per_epoch:
#        print 'Epoch {}...'.format(i/num_minis_per_epoch)
#        
#    batch_idxs = next(train_batch)
#    
#    X = X_train[batch_idxs]
#    train_dict = dict(produce_labels(labels, class_sizes, ys_train[:, batch_idxs]))
#    train_dict.update({'input': X})
#
#    train_error = model.train_on_batch(train_dict)
#
#    if not i % 10:
#        print train_error
#        
#        predictions = model.predict({'input': X_val})
#        for label, ys_pred in predictions.items():
#            print '{} accuracy:'.format(label), np.mean(ys_pred.argmax(axis=1) == val_dict[label])