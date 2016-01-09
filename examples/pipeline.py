import operator
import re
from collections import namedtuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from support import word_cloud

import sklearn
from sklearn.linear_model import SGDClassifier
from sklearn.grid_search import GridSearchCV
from sklearn.feature_extraction.text import TfidfVectorizer


def extract_target(abstracts_targets, target):
    """Filter away all columns not relevant to predicting `target`

    abstracts_targets : dataframe consisting of abstracts, pmid, and targets for
    prediction
    target : ct.gov field of interest for prediction

    Additionally filter away abstracts without a label for `target`

    """
    df = abstracts_targets.ix[:, ['abstract', 'pmid', target]]
    df = df[df[target].notnull()] # filter away abstracts with no label
    
    return df

def filter_sparse_classes(df, target, threshold=10):
    """Filters away classes which we have less than `threshold` number of
    examples for.
    
    Parameters
    ----------
    df : dataframe returned from extract_targets()
    target : ct.gov field of interest for prediction
    
    """
    sizes = df.groupby(target).size()

    filtered_df = df[df[target].isin(sizes[sizes >= threshold].index)]

    sprint('Class Breakdown')
    print filtered_df.groupby(target).size()

    return filtered_df

def view_class_examples(df, target):
    """Prints an example abstract for each class of `target`

    df : dataframe returned from filter_sparse_classes()
    target : ct.gov field of interest for prediction

    """
    labels = df[target].unique()

    indexes = [df[df[target] == label].iloc[0].name for label in labels]

    for index in indexes:
        pm_url = 'https://www.google.com/search?q=pmid+' + df.iloc[index].pmid + '&btnI=I' # I'm Feeling Lucky

        print '*'*5, df.iloc[index][target], '*'*5
        print df.iloc[index].abstract

def word_cloud_classes(df, target):
    """Dispaly a word cloud for each class in `target`

    df : dataframe returned from filter_sparse_classes()
    target : ct.gov field of interest for prediction

    """
    labels = df[target].unique()

    fig = plt.figure(figsize=(12, 2*len(labels)))
    plt.clf()

    for i, label in enumerate(np.sort(labels), start=1):
        axes = fig.add_subplot(int(np.ceil(len(labels)/2.)), 2, i)
        words = ' '.join(df[df[target] == label].abstract)

        word_cloud(words, axes, label)

    fig.suptitle('Most Common Words per Class')
    plt.axis('off')
    plt.show()

def train_test_split(df, target):
    """Returns a train/test split for abstracts when predicting `target`

    df : dataframe returned from filter_sparse_classes()
    target : ct.gov field of interest for prediction

    """
    return sklearn.cross_validation.train_test_split(df.abstract, df[target])

def vectorize(abstracts_train):
    """Vectorizes abstracts

    abstracts_train : abstracts for training returned from train_test_split()

    A TfidfVectorizer is used with use_idf=False in order to make the change to
    using a HashingVectorizer in the future simple

    """
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words='english', use_idf=False, binary=True) # HashingVectorizer
    vectorizer.fit(abstracts_train)

    return vectorizer.transform(abstracts_train), vectorizer

def get_vocabulary(vectorizer):
    """Extract and order vocabulary from `vectorizer`

    vectorizer : vectorizer returned from vectorize()

    This function only needs to be called when we are interested in doing model
    introspection (e.g. plotting word clouds and finding the most important
    words

    """
    return [word for word, index in sorted(vectorizer.vocabulary_.items(), key=operator.itemgetter(1))]

def do_grid_search(X_train, ys_train, k=5, num_alphas=10):
    """Do a grid search over regularization term

    X_train : training set examples
    ys_train : training set labels
    k : number of folds to use in cross-validation
    num_alphas : number of alphas to search over

    Macro f1 scores for each setting of the regularization term are also
    plotted.

    """
    M, N = X_train.shape

    clf = SGDClassifier(class_weight='auto', n_iter=int(np.ceil(10**6/(M-M/k)))) # http://scikit-learn.org/stable/modules/sgd.html#tips-on-practical-use

    parameters = {
        'alpha': np.logspace(-1, -4, num_alphas)
    }

    grid_search = GridSearchCV(clf, parameters, verbose=3, scoring='f1_macro', cv=k)
    grid_search.fit(X_train, ys_train)

    # Get scores for different hyperparam settings into dataframe
    df = pd.DataFrame(grid_search.grid_scores_, columns=grid_search.grid_scores_[0]._fields)

    # Explode cv scores for each hyperparam setting
    scores = df.cv_validation_scores.apply(pd.Series)
    scores = scores.rename(columns=lambda x: 's{}'.format(x))
    score_columns = scores.columns

    scores['f1'], scores['err'] = scores.mean(axis=1), scores.std(axis=1) # mean f1 and stddev for cv scores

    alphas = df.parameters.apply(lambda x: pd.Series(x))

    df = pd.concat([alphas, scores], axis=1).fillna(0) # concatenate the two back together

    # Plot f1 and all the scores for each hyperparam setting
    axes = df['f1'].plot(yerr=df.err, linewidth=.5)
    for s in score_columns:
        axes = df[s].plot(ax=axes, style='.', c='black')

    # Fix axes
    tick_marks = np.arange(len(alphas))
    plt.xticks(tick_marks, df.alpha.round(4), rotation=90)
    axes.set_xlabel('alpha')
    axes.set_ylabel('macro f1')
    
    return grid_search

def predict(clf, abstracts_test, ys_test, vectorizer, verbose=True):
    """Predict test labels

    clf : classifier used in prediction
    abstracts_test : test abstract examples
    ys_test : test abstract labels
    vectorizer : vectorizer used to vectorize train abstract examples
    verbose : print performance numbers if True

    """
    X_test = vectorizer.transform(abstracts_test)
    predictions = clf.predict(X_test)
    
    if verbose:
        # Compute f1s for all classes
        lb = sklearn.preprocessing.LabelBinarizer()
        f1s = sklearn.metrics.f1_score(lb.fit_transform(ys_test), lb.fit_transform(predictions), average=None)

        # Display f1s
        Classes = namedtuple('Classes', [re.sub('[^0-9a-zA-Z]+', '_', class_) for class_ in clf.classes_])

        sprint('Performance')
        print 'f1s: {}'.format({label: f1 for label, f1 in zip(clf.classes_, f1s)})
        print
        print 'Average: {}'.format(np.mean(f1s))
    
    return predictions

def print_confusion_matrix(ys_test, predictions, clf):
    """Print confusion matrix

    ys_test : test abstract labels
    predictions : test abstract label predictions
    clf : classifer used to make predictions

    """
    confusion_matrix = sklearn.metrics.confusion_matrix(ys_test, predictions)

    fig = plt.figure()
    plt.clf()

    labels = clf.classes_

    plt.imshow(confusion_matrix, cmap=plt.cm.Blues, interpolation='nearest')
    plt.title('Confusion Matrix')
    tick_marks = np.arange(len(labels))
    plt.xticks(tick_marks, labels, rotation=90)
    plt.yticks(tick_marks, labels)
    plt.ylabel('True label')
    plt.xlabel('Predicted label')

    width = height = len(labels)

    for x in xrange(width):
        for y in xrange(height):
            plt.annotate(str(confusion_matrix[x][y]) if confusion_matrix[x][y] else '', xy=(y, x), 
                        horizontalalignment='center',
                        verticalalignment='center')

def duplicate_words(pairs):
    """Helper function which yields a number of duplicated words proportional to
    their corresponding coefficients"""

    for coef, word in pairs:
        for _ in range(int(coef*100)):
            yield word

def most_important_features(clf, vocabulary):
    """Display word clouds of most important features

    clf : trained classifier
    vocabulary : list of words in same order as clf features

    """
    fig = plt.figure(figsize=(20, 20))
    plt.clf()

    labels = clf.classes_
    for i, (weights, title) in enumerate(zip(clf.coef_, labels), start=1):
        pairs = sorted(zip(weights, vocabulary), reverse=True)[:10]
        pairs = [(pair[0], re.sub('\s+', '_', pair[1])) for pair in pairs]

        duped_words = list(duplicate_words(pairs))

        axes = fig.add_subplot(int(np.ceil(len(labels)/2.)), 2, i)
        word_cloud(' '.join(duped_words), axes, title)

    fig.suptitle('Most Important Words per Class')

    plt.axis('off')
    plt.show()

def do_pipeline(abstracts_targets, target):
    """Execute ct.gov fixed-class prediction pipeline

    1. Extract targets
    2. Filter away sparse classes
        - This box is necessary because sklearn.metrics.f1_score() complains
          when there's a class in the prediction set that's not in the true_y
          set.  Additionally having a small number of classes hurts overall
          performance due to the fact macro_f1 scoring is currently being used.
    3. View class examples (optional)
    4. Word cloud classes (optional)
    5. Train/test split
    6. Vectorize training set
    7. Extract ordered vocabulary (for model introspection - optional)
    8. Grid search over regularization terms
    9. Extract best estimator
    10. Make predictions and evaluate performance
    11. Print confusion matrix (optional)
    12. Display most important features (optional)

    """
    
    df = extract_target(abstracts_targets, target)
    df = filter_sparse_classes(df, target)
    # view_class_examples(df, 'intervention_model')
    print
    word_cloud_classes(df, target)
    abstracts_train, abstracts_test, ys_train, ys_test = train_test_split(df, target) 
    X_train, vectorizer = vectorize(abstracts_train)
    vocabulary = get_vocabulary(vectorizer)
    sprint('Grid Search')
    grid_search = do_grid_search(X_train, ys_train, k=3, num_alphas=5)
    best_clf = grid_search.best_estimator_
    predictions = predict(best_clf, abstracts_test, ys_test, vectorizer)           
    print_confusion_matrix(ys_test, predictions, best_clf)
    most_important_features(best_clf, vocabulary)

def sprint(message):
    """Helper function for printing eye catching messages"""

    print '*'*5, message, '*'*5