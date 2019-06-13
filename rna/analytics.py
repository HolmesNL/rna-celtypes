"""
Performs project specific.
"""

import numpy as np

from rna.constants import single_cell_types

from lir.lr import calculate_cllr


def combine_samples(data_for_class):
    """
    Combines the repeated measurements for each sample.

    :param data_for_class: N_samples x N_observations_per_sample x N_markers measurements numpy array
    :return: N_samples x N_markers measurements numpy array
    """
    data_for_class_mean = np.array([np.mean(data_for_class[i], axis=0)
                                    for i in range(data_for_class.shape[0])])
    return data_for_class_mean


def construct_random_samples(X, y, n, classes_to_include, n_features):
    """
    Returns n generated samples that contain classes classes_to_include.
    A sample is generated by random sampling a sample for each class, and adding
    the shuffled replicates.

    :param X: N_single_cell_experimental_samples array and within a list filled with
        for each n_single_cell_experimental_sample a N_measurements per sample x N_markers array
    :param y: list of length N_single_cell_experimental_samples filled with int labels of which
        cell type was measured
    :param n: number of samples to generate
    :param classes_to_include: iterable of int, cell type indices to include
        in the mixtures
    :param n_features: int N_markers (=N_features)
    :return: n x n_features array
    """
    if len(classes_to_include) == 0:
        return np.zeros((n, n_features))
    data_for_class=[]
    for clas in classes_to_include:
        data_for_class.append(X[np.argwhere(np.array(y) == clas)[:, 0]])

    augmented_samples = []
    for i in range(n):
        sampled = []
        for j, clas in enumerate(classes_to_include):

            n_in_class = sum(np.array(y) == clas)
            sampled_sample = data_for_class[j][np.random.randint(n_in_class)]
            n_replicates = len(sampled_sample)
            sampled.append(sampled_sample[np.random.permutation(n_replicates)])
        # TODO thus lower replicates for more cell types. is this an issue?
        # print("Smallest replicates:", smallest_replicates)
        # for sample in sampled:
        #     print("Length sample in samples:", len(sample))
        # ---------------------------------------------------
        # Smallest replicates: 2
        # Length sample in samples: 4
        # Length sample in samples: 4
        # Length sample in samples: 4
        # Length sample in samples: 2
        smallest_replicates = min([len(sample) for sample in sampled])

        combined_sample = []
        for i_replicate in range(smallest_replicates):
            combined_sample.append(np.mean(np.array([sample[i_replicate] for sample in sampled]), axis=0))
            # TODO: Should take same here instead of mean?
            # combined_sample.append(np.sum(np.array([sample[i_replicate] for sample in sampled]), axis=0))

        augmented_samples.append(combined_sample)
    return combine_samples(np.array(augmented_samples))


def augment_data(X, y, n_celltypes, n_features, N_SAMPLES_PER_COMBINATION,
                 label_encoder, binarize=False, from_penile=False):
    """
    Generate data for the power set of single cell types

    :param X: n_samples x n_measurements per sample x n_markers array of measurements
    :param y_nhot: n_samples x n_celltypes_with_penile array of int labels of which
        cell type was measured
    :param n_celltypes: int: number of single cell types
    :param n_features: int: n_markers
    :param N_SAMPLES_PER_COMBINATION:
    :param label_encoder:
    :param from_penile: bool: generate sample that (T) always or (F) never
        also contain penile skin
    :return: n_experiments x n_markers array,
             n_experiments x n_celltypes matrix of 0, 1 indicating for each augmented sample
                which single cell type it was made up of. Does not contain column for penile skin
    """

    if X.size == 0:
        # This is the case when calibration_size = 0.0, this is an implicit way to
        # ensure that calibration is not performed.
        X_augmented=None
        y_nhot_augmented=np.zeros((0, n_celltypes))

    else:
        X_augmented = np.zeros((0, n_features))
        y_nhot_augmented = np.zeros((2 ** n_celltypes * N_SAMPLES_PER_COMBINATION,
                                     n_celltypes), dtype=int)

        # for each possible combination augment N_SAMPLES_PER_COMBINATION
        for i in range(2 ** n_celltypes):
            binary = bin(i)[2:]
            while len(binary) < n_celltypes:
                binary = '0' + binary

            classes_in_current_mixture = []
            for i_celltype in range(len(label_encoder.classes_)):
                if binary[-i_celltype - 1] == '1':
                    classes_in_current_mixture.append(i_celltype)
                    y_nhot_augmented[i * N_SAMPLES_PER_COMBINATION:(i + 1) * N_SAMPLES_PER_COMBINATION, i_celltype] = 1
            if from_penile:
                # also (always) add penile skin samples. the index for penile is n_celltypes
                y_nhot_augmented[i * N_SAMPLES_PER_COMBINATION:(i + 1) * N_SAMPLES_PER_COMBINATION, n_celltypes] = 1
                classes_in_current_mixture.append(n_celltypes)

            X_augmented = np.append(X_augmented, construct_random_samples(
                X, y, N_SAMPLES_PER_COMBINATION, classes_in_current_mixture, n_features), axis=0)

        if binarize:
            X_augmented = np.where(X_augmented > 150, 1, 0)
        else: # normalize
            X_augmented = X_augmented / 1000
            # X_augmented = normalize(X_augmented)

    return X_augmented, y_nhot_augmented[:, :n_celltypes]


def get_mixture_columns_for_class(target_class, priors):
    """
    for the target_class, a vector of length n_single_cell_types with 1 or more 1's, give
    back the columns in the mixtures that contain one or more of these single cell types

    :param target_class: vector of length n_single_cell_types with at least one 1
    :param priors: vector of length n_single_cell_types with 0 or 1 to indicate single cell type has 0 or 1 prior,
    uniform assumed otherwise
    :return: list of ints, in [0, 2 ** n_cell_types]
    """

    def int_to_binary(i):
        binary = bin(i)[2:]
        while len(binary) < len(single_cell_types):
            binary = '0' + binary
        return np.flip([int(j) for j in binary]).tolist()

    def binary_admissable(binary, target_class, priors):
        """
        gives back whether the binary (string of 0 and 1 of length n_single_cell_types) has at least one of
        target_class in it, and all priors satisfied
        """
        if priors:
            for i in range(len(target_class)):
                # if prior is zero, the class should not occur
                if binary[i] == 1 and priors[i] == 0:
                    return False
                # if prior is one, the class should occur
                # as binary is zero it does not occur and return False
                if binary[i] == 0 and priors[i] == 1:
                    return False
        # at least one of the target class should occur
        if np.inner(binary, target_class)==0:
            return False
        return True

    return [i for i in range(2 ** len(single_cell_types)) if binary_admissable(int_to_binary(i), target_class, priors)]


def cllr(lrs, y_nhot, target_class):
    """
    Computes the cllr for one celltype.

    :param lrs: numpy array: N_samples with the LRs from the method
    :param y_nhot: N_samples x N_single_cell_type n_hot encoding of the labels
    :param target_class: vector of length n_single_cell_types with at least one 1
    :return: float: the log-likehood cost ratio
    """

    lrs1 = np.multiply(lrs, np.max(np.multiply(y_nhot, target_class), axis=1))
    lrs2 = np.multiply(lrs, 1 - np.max(np.multiply(y_nhot, target_class), axis=1))

    # delete zeros
    lrs1 = np.delete(lrs1, np.where(lrs1 == 0.0))
    lrs2 = np.delete(lrs2, np.where(lrs2 == 0.0))

    if len(lrs1) > 0 and len(lrs2) > 0:
        return calculate_cllr(lrs2, lrs1).cllr
    else:
        return 9999.0000