try:
    from .uclchem import wrap
except:
    print("No UCLCHEM module, run ``make python'' in src/")
    print("Utility and plotting functions available but UCLCHEM based functions will fail\n\n")
from .analysis import *

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from seaborn import color_palette

elementList = [
    "H",
    "D",
    "HE",
    "C",
    "N",
    "O",
    "F",
    "P",
    "S",
    "CL",
    "LI",
    "NA",
    "MG",
    "SI",
    "PAH",
    "15N",
    "13C",
    "18O",
    "SURFACE",
    "BULK",
]


def run_model(param_dict):
    """
    Run UCLCHEM using variables taking from a dictionary of parameter values. Any parameter
    not included in the dictionary will be taken from defaultparameters.f90.

    :param param_dict: A dictionary of parameters where keys are any of the variables in defaultparameters.f90 and values are value for current run.
    """
    param_dict = param_dict.copy()
    outSpecies = param_dict["outSpecies"]
    param_dict["outSpecies"] = len(outSpecies.split())

    success_flag = wrap.run_model_to_file(dictionary=param_dict, outspeciesin=outSpecies)
    return success_flag


def run_model_for_abundances(param_dict):
    """
    Run UCLCHEM, returning the abundances of up to 50 species at the end of the run. The species that will be returned are those from the `outSpecies` parameter.

    :param param_dict: A dictionary of parameters where keys are any of the variables in defaultparameters.f90 and values are value for current run.

    :returns: (ndarray) Array of abundances of all species in `outSpecies`
    """
    param_dict = param_dict.copy()
    outSpecies = param_dict["outSpecies"]
    param_dict["outSpecies"] = len(outSpecies.split())

    abunds,success_flag = wrap.run_model_for_abundances(dictionary=param_dict, outspeciesin=outSpecies)
    if success_flag==1:
        return abunds[: param_dict["outSpecies"]]
    else:
        return np.nan


def get_species_rates(param_dict, input_abundances, reac_indxs):
    """
    Get the rate of up to 500 reactions from UCLCHEM for a given set of parameters and abundances.
    Intended for use within the analysis script.
    :param param_dict:  A dictionary of parameters where keys are any of the variables in defaultparameters.f90 and values are value for current run.
    :param input_abundances: Abundance of every species in network
    :param reac_indxs: Index of reactions of interest in the network's reaction list.

    :returns: (ndarray) Array containing the rate of every reaction specified by reac_indxs
    """
    input_abund = np.zeros(500)
    input_abund[: len(input_abundances)] = input_abundances
    rate_indxs = np.zeros(500)
    rate_indxs[: len(reac_indxs)] = reac_indxs
    rates = wrap.get_rates(param_dict, input_abund, rate_indxs)
    return rates[: len(reac_indxs)]


def read_output_file(output_file):
    """
    Read the output of a UCLCHEM run created with the outputFile parameter into a pandas DataFrame

    :param output_file: - (str) path to file containing a full UCLCHEM output

    :return: (dataframe) A dataframe containing the abundances and physical parameters of the model at every time step.
    """
    f = open(output_file)
    f.readline()
    bits = f.readline().split()
    radfield = float(bits[1])
    zeta = float(bits[3])
    data = pd.read_csv(f)
    data["zeta"] = zeta
    data["radfield"] = radfield
    data.columns = data.columns.str.strip()
    return data


def create_abundance_plot(df, species, plot_file=None):
    """
    Produce a plot of the abundances of chosen species through time, returning the pyplot
    figure and axis objects

    :param df: A dataframe created by `read_output_file`
    :param species: A list of species names to be plotted
    :param plot_file: optional argument with path to file where the plot should be saved

    :return: fig (matplotlib figure) A figure object and ax (matplotlib axis) An axis object which contains the plot
    """
    fig, ax = plt.subplots()

    ax = plot_species(ax, df, species)
    ax.legend(loc=4, fontsize="small")

    ax.set_xlabel("Time / years")
    ax.set_ylabel("X$_{Species}$")

    ax.set_yscale("log")
    if plot_file is not None:
        fig.savefig(plot_file)
    return fig, ax


def plot_species(ax, df, species):
    """
    Plot the abundance of several species through time onto an existing pyplot axis

    :param ax: pyplot axis on which to plot
    :param df: A dataframe created by `read_output_file`
    :param species: A list of species names to be plotted

    :returns: ax (matplotlib ax) The input axis is returned
    """
    color_palette(n_colors=len(species))
    for specIndx, specName in enumerate(species):
        if specName[0] == "$":
            abundances = df[specName.replace("$", "#")]
            if specName.replace("$", "@") in df.columns:
                abundances = abundances + df[specName.replace("$", "@")]
        else:
            if specName in df.columns:
                abundances = df[specName]
            else:
                print(f"{specName} not found in dataframe")
                return None
        ax.plot(df["Time"], abundances, label=specName, lw=2)
        ax.set(yscale="log")
        ax.legend()
    return ax


def param_dict_from_output(output_line):
    """
    Generate a parameter dictionary with enough variables to correctly estimate the rates of
    reactions.

    :param output_line: (pandas series) any row from the relevant UCLCHEM output
    """
    param_dict = {
        "initialDens": output_line["Density"],
        "initialTemp": output_line["gasTemp"],
        "zeta": output_line["zeta"],
        "radfield": output_line["radfield"],
        "baseAv": 0.0,
        "rout": output_line["av"] * (1.6e21) / output_line["Density"],
    }
    return param_dict


def count_element(species_list, element):
    """
    Count the number of atoms of an element that appear in each of a list of species,
    return the array of counts

    :param  species_list: (iterable, str), list of species names
    :param element: (str), element

    :return: sums (ndarray) array where each element represents the number of atoms of the chemical element in the corresponding element of species_list
    """
    species_list = pd.Series(species_list)
    # confuse list contains elements whose symbols contain the target eg CL for C
    # We count both sets of species and remove the confuse list counts.
    confuse_list = [x for x in elementList if element in x]
    confuse_list = sorted(confuse_list, key=lambda x: len(x), reverse=True)
    confuse_list.remove(element)
    sums = species_list.str.count(element)
    for i in range(2, 10):
        sums += np.where(species_list.str.contains(element + f"{i:.0f}"), i - 1, 0)
    for spec in confuse_list:
        sums += np.where(species_list.str.contains(spec), -1, 0)
    return sums


def total_element_abundance(element, df):
    """
    Calculates that the total elemental abundance of a species as a function of time. Allows you to check conservation.

    :param element: (str) Element symbol. eg "C"
    :param df: (pandas dataframe) UCLCHEM output in format from `read_output_file`

    :return: Series containing the total abundance of an element at every time step of your output
    """
    sums = count_element(df.columns, element)
    for variable in ["Time", "Density", "gasTemp", "av", "point", "SURFACE", "BULK"]:
        sums = np.where(df.columns == variable, 0, sums)
    return df.mul(sums, axis=1).sum(axis=1)


def check_element_conservation(df, element_list=["H", "N", "C", "O"]):
    """
    Check the conservation of major element by comparing total abundance at start and end of model

    :param	df: (pandas dataframe): UCLCHEM output in format from `read_output_file`

    :return: (dict) Dictionary containing the change in the total abundance of each element as a fraction of initial value
    """
    result = {}
    for element in element_list:
        discrep = total_element_abundance(element, df).values
        discrep = np.abs(discrep[0] - discrep[-1]) / discrep[0]
        result[element] = discrep
    return result


def test_ode_conservation(species_list, element_list=["H", "N", "C", "O"]):
    """Test function which checks whether the ODEs conserve elementsry_

    :param species_list (list): list of each species in the network

    :return: (dict) Dictionary containing total rate of change of important elements
    """
    param_dict = {
        "phase": 1,
        "switch": 0,
        "collapse": 1,
        "writeStep": 1,
        "initialDens": 1e4,
        "initialTemp": 10.0,
        "finalDens": 1e5,
        "finalTime": 1.0e3,
        "outSpecies": " ".join(species_list),
    }
    abundances = run_model_for_abundances(param_dict)
    param_dict.pop("outSpecies")
    input_abund = np.zeros(500)
    input_abund[: len(abundances)] = abundances
    rates = wrap.get_odes(param_dict, input_abund)
    df = pd.DataFrame(columns=species_list)
    df.loc[len(df)] = rates[: len(species_list)]
    result = {}
    for element in element_list:
        discrep = total_element_abundance(element, df).values
        result[element] = discrep[0]
    return result
