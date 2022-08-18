from deap import base, creator, tools, algorithms
from scipy.stats import bernoulli
from bitstring import BitArray
import time
import tensorflow as tf
import pandas as pd
from nnogada.hyperparameters import *

class Nnogada:
    def __init__(self, hyp_to_find, X_train, Y_train, X_val, Y_val, regression=True,
                 **kwargs):
        """
        Initialization of Nnogada class.

        Parameters
        -----------
        hyp_to_find: dict
            Dictionary with the free hyperparameters of the neural net. The names must match with the names
            in the hyperparameters.py file.
            Ex: hyperparams = {'deep': [2,3], 'num_units': [100, 200], 'batch_size': [8, 32]}

        X_train: numpy.ndarray
            Set of attributes, or independent variables, for training.

        Y_train: numpy.ndarray
            Set of labels or dependent variable for training.

        X_val: numpy.ndarray
            Set of attributes, or independent variables, for testing/validation.

        Y_test: numpy.ndarray
            Set of labels or dependent variable for testing/validation.

        regression: Boolean
            If True assumes a regression task. Else, a classification is assumed. It
            affects the default choice in the activation function for the last layer,
            if regression it is the linear function, else it is softmax.

        **kwargs
        --------
            deep: Hyperparameter object
                Number of layers.

            num_units: Hyperparameter object
                Number of nodes by layer.

            batch_size: Hyperparameter object
                Batch size.

            learning_rate: Hyperparameter object
                Learning rate for Adam optimizer.

            epochs: Hyperparameter object
                Number of epochs for training.

            act_fn: Hyperparameter object
                Activation function for the hidden layers.

            last_act_fn: Hyperparameter object
                Activation function for the last layer.

            loss_fn: Hyperparameter object
                Loss function.

        """
        self.deep = kwargs.pop('deep', deep)
        self.num_units = kwargs.pop('num_units', num_units)
        self.batch_size = kwargs.pop('batch_size', batch_size)
        self.learning_rate = kwargs.pop('learning_rate', learning_rate)
        self.epochs = kwargs.pop('epochs', epochs)
        self.act_fn = kwargs.pop('act_fn', act_fn)
        self.last_act_fn = kwargs.pop('last_act_fn', last_act_fn)
        self.loss_fn = kwargs.pop('loss_fn', loss_fn)

        self.all_hyp_list = [self.deep, self.num_units, self.batch_size, self.learning_rate,
                             self.epochs, self.act_fn, self.last_act_fn, self.loss_fn]

        self.hyp_to_find = hyp_to_find

        if regression:
            self.metric = 'mean_squared_error'
        else:
            # it is a classification problem
            self.metric = 'accuracy'
            self.last_act_fn.setVal('softmax')

        self.X_train = X_train
        self.Y_train = Y_train
        self.X_val = X_val
        self.Y_val = Y_val

        self.history = []
    def set_hyperparameters(self):
        """
        This small routine sets as variable the hyperparameters
        indicated in the hyp_to_find dictionary.
        """
        for hyp in self.all_hyp_list:
            if hyp.name in self.hyp_to_find:
                hyp.vary = True
                hyp.setValues(self.hyp_to_find[hyp.name]) #SC_hyperparameters

    def neural_train_evaluate(self, ga_individual_solution):
        """
        This train and evaluates the neural network models with the different
        solutions proposed by the Genetic Algorithm .

        Parameters
        -----------

        ga_individual_solution:
            Individual of the genetic algorithm.
        """
        t = time.time()
        # Decode GA solution to integer for window_size and num_units
        hyp_vary_list = []
        self.df_colnames = []
        for i, hyp in enumerate(self.all_hyp_list):
            if hyp.vary:
                hyp.bitarray = BitArray(ga_individual_solution[i:i+1])  # (8)
                hyp.setVal(hyp.values[hyp.bitarray.uint])
                hyp_vary_list.append(hyp.val)
                self.df_colnames.append(hyp.name)
                print(hyp.name + ": {} | ".format(hyp.val), end='')
        print("\n-------------------------------------------------")

        # Train model and predict on validation set
        model = tf.keras.Sequential()
        model.add(tf.keras.layers.Dense(self.num_units.val, input_shape=(int(self.X_train.shape[1]),)))

        for i in range(self.deep.val):
            model.add(tf.keras.layers.Dense(self.num_units.val, activation=self.act_fn.val))
        #             model.add(keras.layers.Dropout(0.3))
        # model.add(tf.keras.layers.Dense(int(self.Y_train.shape[1]), activation=tf.nn.softmax))
        model.add(tf.keras.layers.Dense(int(self.Y_train.shape[1]), activation=self.last_act_fn.val))

        optimizer = tf.keras.optimizers.Adam(learning_rate=self.learning_rate.val, beta_1=0.9, beta_2=0.999, epsilon=1e-3)
        model.compile(optimizer=optimizer, loss=self.loss_fn.val, metrics=[self.metric])
        model.fit(self.X_train, self.Y_train, epochs=self.epochs.val, validation_data=(self.X_val, self.Y_val),
                  callbacks=None, batch_size=self.batch_size.val, shuffle=1, verbose=0)

        loss, score = model.evaluate(self.X_val, self.Y_val)
        t = time.time() - t
        print("Accuracy: {:.5f} Loss: {:.5f} Elapsed time: {:.2f}".format(score, loss, t))
        print("-------------------------------------------------\n")

        # results = [hyp for hyp in hyp_vary_list].extend([loss, score, t])
        # print(results)
        self.history.append(hyp_vary_list+[loss, score, t])
        return loss,

    def eaSimpleWithElitism(self, population, toolbox, cxpb, mutpb, ngen, stats=None,
                            halloffame=None, verbose=__debug__):
        """
        Method from https://github.com/PacktPublishing/Hands-On-Genetic-Algorithms-with-Python.

        This algorithm is similar to DEAP eaSimple() algorithm, with the modification that
        halloffame is used to implement an elitism mechanism. The individuals contained in the
        halloffame are directly injected into the next generation and are not subject to the
        genetic operators of selection, crossover and mutation.
        """
        logbook = tools.Logbook()
        logbook.header = ['gen', 'nevals'] + (stats.fields if stats else [])

        # Evaluate the individuals with an invalid fitness
        invalid_ind = [ind for ind in population if not ind.fitness.valid]
        fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit

        if halloffame is None:
            raise ValueError("halloffame parameter must not be empty!")

        halloffame.update(population)
        hof_size = len(halloffame.items) if halloffame.items else 0

        record = stats.compile(population) if stats else {}
        logbook.record(gen=0, nevals=len(invalid_ind), **record)
        if verbose:
            print(logbook.stream)

        # Begin the generational process
        for gen in range(1, ngen + 1):

            # Select the next generation individuals
            offspring = toolbox.select(population, len(population) - hof_size)

            # Vary the pool of individuals
            offspring = algorithms.varAnd(offspring, toolbox, cxpb, mutpb)

            # Evaluate the individuals with an invalid fitness
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit

            # add the best back to population:
            offspring.extend(halloffame.items)

            # Update the hall of fame with the generated individuals
            halloffame.update(offspring)

            # Replace the current population by the offspring
            population[:] = offspring

            # Append the current generation statistics to the logbook
            record = stats.compile(population) if stats else {}
            logbook.record(gen=gen, nevals=len(invalid_ind), **record)
            if verbose:
                print(logbook.stream)

        return population, logbook

    def ga_with_elitism(self, population_size, max_generations, gene_length, k,
                        pmutation=0.5, pcrossover=0.5, hof=1):
        """
        Simple genetic algorithm with elitism.

        Parameters:
        ------------

        population_size: int
            Population size.

        max_generations: int
            Maximum number of generations.

        gene_length: int
            Length of each gene.

        k: int
            K parameter for the tournament selection method.

        pmutation: float
            Probability of mutation (0<pmutation<1)

        pcrossover: float
            Probability of crossover (0<pcrossover<1)

        hof: int
            Number of individuals to stay in the hall of fame. It determines
            the elitism performance.
        """
        # Genetic Algorithm constants:
        P_CROSSOVER = pcrossover  # probability for crossover
        P_MUTATION = pmutation  # probability for mutating an individual
        HALL_OF_FAME_SIZE = hof  # Best individuals that pass to the other generation

        # set the random seed:
        toolbox = base.Toolbox()

        # As we are trying to minimize the RMSE score, that's why using -1.0.
        # In case, when you want to maximize accuracy for instance, use 1.0
        creator.create('FitnessMin', base.Fitness, weights=[-1.0])
        creator.create('Individual', list, fitness=creator.FitnessMin)

        # create the individual operator to fill up an Individual instance:
        toolbox.register('binary', bernoulli.rvs, 0.5)
        toolbox.register('individual', tools.initRepeat, creator.Individual, toolbox.binary, n=gene_length)

        # create the population operator to generate a list of individuals:
        toolbox.register('population', tools.initRepeat, list, toolbox.individual)

        # genetic operators:
        toolbox.register('evaluate', self.neural_train_evaluate)
        toolbox.register('select', tools.selTournament, tournsize=2)
        toolbox.register('mutate', tools.mutFlipBit, indpb=0.11)
        toolbox.register('mate', tools.cxUniform, indpb=0.5)

        # create initial population (generation 0):
        population = toolbox.population(n=population_size)

        # prepare the statistics object:
        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("min", np.min)
        stats.register("avg", np.mean)
        stats.register("max", np.max)

        # define the hall-of-fame object:
        hof = tools.HallOfFame(HALL_OF_FAME_SIZE)

        # Genetic Algorithm flow with elitism:
        population, logbook = self.eaSimpleWithElitism(population, toolbox, cxpb=P_CROSSOVER, mutpb=P_MUTATION,
                                                       ngen=max_generations, stats=stats, halloffame=hof, verbose=True)

        # print info for best solution found:
        best = hof.items[0]
        # print("-- Best Individual = ", best)
        # print("-- Best Fitness = ", best.fitness.values[0])

        # extract statistics:
        minFitnessValues, meanFitnessValues, maxFitnessValues = logbook.select("min", "max", "avg")
        print(best.fitness.values)

        # # plot statistics:
        # sns.set_style("whitegrid")
        # plt.plot(minFitnessValues, color='blue', label="Min")
        # plt.plot(meanFitnessValues, color='green', label="Mean")
        # plt.plot(maxFitnessValues, color='red', label="Max")
        # plt.xlabel('Generation');
        # plt.ylabel('Max / Min / Average Fitness')
        # plt.legend()
        # plt.title('Max, Min and Average fitness over Generations')
        # plt.show()

        best_population = tools.selBest(population, k=k)
        # convert the history list in a data frame
        # print(self.history.head(5))
        self.df_colnames = self.df_colnames + ['loss', 'score', 't']
        print(self.df_colnames)
        self.history = pd.DataFrame(self.history, columns=self.df_colnames)
        self.history = self.history.sort_values(by='loss', ascending=True)
        print(self.history.head(5))

        return best_population