#! /usr/bin/python
import math
import os
import string
import struct
import sys
import time
import csv
import numpy

#functions including
#1. simple classes to store all the information about each species and reaction.
#2. Functions to read in the species and reaction file and check for sanity
#3. Functions to write out files necessary for UCLCHEM


##########################################################################################
#1. simple classes to store all the information about each species and reaction.
#largely just to make the other functions more readable.
##########################################################################################
class Species:
	def __init__(self,inputRow):
		self.name=inputRow[0]
		self.mass=inputRow[1]
		self.bindener=inputRow[2]
		self.solidFraction=inputRow[3]
		self.monoFraction=inputRow[4]
		self.volcFraction=inputRow[5]
		self.enthalpy=inputRow[6]

class Reaction:
	def __init__(self,inputRow):
		self.reactants=[inputRow[0],inputRow[1],self.NANCheck(inputRow[2])]
		self.products=[inputRow[3],self.NANCheck(inputRow[4]),self.NANCheck(inputRow[5]),self.NANCheck(inputRow[6])]
		self.alpha=inputRow[7]
		self.beta=inputRow[8]
		self.gamma=inputRow[9]
		self.templow=inputRow[10]
		self.temphigh=inputRow[11]

	def NANCheck(self,a):
		aa  = a if a else 'NAN'
		return aa




##########################################################################################
#2. Functions to read in the species and reaction file and check for sanity
##########################################################################################

# Read the entries in the specified species file
def read_species_file(fileName):
	speciesList=[]
	f = open(fileName, 'rb')
	reader = csv.reader(f, delimiter=',', quotechar='|')
	for row in reader:
		if row[0]!="NAME":
			speciesList.append(Species(row))
	nSpecies = len(speciesList)
	return nSpecies,speciesList

# Read the entries in the specified reaction file and keep the reactions that involve the species in our species list
def read_reaction_file(fileName, speciesList, ftype):
	reactions=[]
	keepList=[]
	# keeplist includes the elements that ALL the reactions should be formed from 
	keepList.extend(['','NAN','#','E-','e-','ELECTR','PHOTON','CRP','CRPHOT','FREEZE','CRH','PHOTD','THERM','XRAY','XRSEC','XRLYA','XRPHOT','DESOH2','DESCR','DEUVCR'])
	for species in speciesList:
		keepList.append(species.name)			                                  
	if ftype == 'UMIST': # if it is a umist database file
		f = open(fileName, 'rb')
		reader = csv.reader(f, delimiter=':', quotechar='|')
		for row in reader:
			if all(x in keepList for x in [row[2],row[3],row[4],row[5],row[6],row[7]]): #if all the reaction elements belong to the keeplist
				#umist file doesn't have third reactant so add space and has a note for how reactions there are so remove that
				reactions.append(Reaction(row[2:4]+['']+row[4:8]+row[9:]))
	if ftype == 'UCL':	# if it is a ucl made (grain?) reaction file
		f = open(fileName, 'rb')
		reader = csv.reader(f, delimiter=',', quotechar='|')
		for row in reader:
			if all(x in keepList for x in row[0:7]):	#if all the reaction elements belong to the keeplist
				row[10]=0.0
				row[11]=10000.0
				reactions.append(Reaction(row))	

	nReactions = len(reactions)
	return nReactions, reactions

#Look for possibly incorrect parts of species list
def filter_species(speciesList,reactionList):
	#check for species not involved in any reactions
	lostSpecies=[]
	for species in speciesList:
		keepFlag=False
		for reaction in reactionList:
			if species.name in reaction.reactants or species.name in reaction.products:
				keepFlag=True
		if not keepFlag:
			lostSpecies.append(species.name)
			speciesList.remove(species)

	#check for duplicate species
	duplicates=0
	duplicate_list=[]
	for i in range(0,len(speciesList)):
		for j in range(0,len(speciesList)):
			if speciesList[i].name==speciesList[j].name:
				if (j!=i) and speciesList[i].name not in duplicate_list:
					print "\t {0} appears twice in input species list".format(speciesList[i].name)
					duplicate_list.append(speciesList[i].name)

	for duplicate in duplicate_list:
		removed=False
		i=0
		while not removed:
			if speciesList[i].name==duplicate:
				del speciesList[i]
				print "\tOne entry of {0} removed from list".format(duplicate)
				removed=True
			else:
				i+=1

	print '\tSpecies in input list that do not appear in final list:' 
	print '\t',lostSpecies
	print '\n'
	return speciesList

#check reactions to alert user of potential issues including repeat reactions
#and multiple freeze out routes
def reaction_check(speciesList,reactionList):


	#first check for multiple freeze outs so user knows to do alphas
	print "\tSpecies with multiple freeze outs, check alphas:"
	for spec in speciesList:
		freezes=0
		for reaction in reactionList:
			if (spec.name in reaction.reactants and 'FREEZE' in reaction.reactants):
				freezes+=1
		if (freezes>1):
			print "\t{0} freezes out through {1} routes".format(spec.name,freezes)
	#now check for duplicate reactions
	duplicate_list=[]
	print "\n\tPossible duplicate reactions for manual removal:"
	duplicates=0
	for i, reaction1 in enumerate(reactionList):
		if i not in duplicate_list:
			for j, reaction2 in enumerate(reactionList):
				if i!=j:
					if set(reaction1.reactants)==set(reaction2.reactants):
						if set(reaction1.products)==set(reaction2.products):
							print "\tReactions {0} and {1} are possible duplicates".format(i+1,j+1)
							print "\t",str(i+1), reaction1.reactants, "-->", reaction1.products 
							print "\t",str(j+1), reaction1.reactants, "-->", reaction2.products 
							duplicates+=1
							duplicate_list.append(i)
							duplicate_list.append(j)
	
	if (duplicates==0):
		print "\tNone"

#capitalize files
def make_capitals(fileName):
	a=open(fileName).read()
	output = open(fileName, mode='w')
	output.write(a.upper())
	output.close()

# Find the elemental constituents and molecular mass of each species in the supplied list
def find_constituents(speciesList):
	elementList=['H','D','HE','C','N','O','F','P','S','CL','LI','NA','MG','SI','PAH']
	elementMass=[1,2,4,12,14,16,19,31,32,35,3,23,24,28,420]
	symbols=['#','+','-']
    
	for species in speciesList:
		speciesName=species.name
		i=0
		atoms=[]
		#loop over characters in species name to work out what it is made of
		while i<len(speciesName):
			#if character isn't a #,+ or - then check it otherwise move on
			if speciesName[i] not in symbols:
				if i+1<len(speciesName):
					#if next two characters are (eg) 'MG' then atom is Mg not M and G
					if speciesName[i:i+2] in elementList:
						j=i+2
					#otherwise work out which element it is
					elif speciesName[i] in elementList:
						j=i+1
				#if there aren't two characters left just try next one
				elif speciesName[i] in elementList:
					j=i+1
				#if we've found a new element check for numbers otherwise print error
				if j>i:
					atoms.append(speciesName[i:j])#add element to list
					if j<len(speciesName):
						if is_number(speciesName[j]):
							for k in range(1,int(speciesName[j])):
								atoms.append(speciesName[i:j])
							i=j+1
						else:
							i=j
					else:
						i=j
				else:
					print"\t{0} contains elements not in element list:".format(speciesName)
					print elementList
			else:
				i+=1
		species.n_atoms=len(atoms)
		mass=0
		for atom in atoms:
			mass+=elementMass[elementList.index(atom)]
		if mass!=float(species.mass):
			print "\tcalculated mass of {0} does not match input mass".format(speciesName)
			print "\tcalculated mass: {0} \t input mass: {1}\n".format(mass,species.mass)
	return speciesList

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
##########################################################################################
#3. Functions to write out files necessary for UCLCHEM
##########################################################################################

# Write the species file in the desired format
def write_species(fileName, speciesList):
	f= open(fileName,'wb')
	writer = csv.writer(f,delimiter=',',quotechar='|',quoting=csv.QUOTE_MINIMAL, lineterminator='\n')		
	nSpecies = len(speciesList)
	f.write(str(nSpecies+1)+'\n')
	for species in speciesList:
		writer.writerow([species.name,species.mass,species.n_atoms])

# Write the reaction file in the desired format
def write_reactions(fileName, reactionList):
	f = open(fileName, 'wb')
	writer = csv.writer(f,delimiter=',',quotechar='|',quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
	nReactions = len(reactionList)
	f.write(str(nReactions)+'\n')
	for reaction in reactionList:
		#if statement changes beta for ion freeze out to 1. This is how ucl_chem recognises ions when calculating freeze out rate
		if ('FREEZE' in reaction.reactants and reaction.reactants[0][-1]=='+'):
			reaction.beta=1
		writer.writerow(reaction.reactants+reaction.products+[reaction.alpha,reaction.beta,reaction.gamma,reaction.templow,reaction.temphigh])

def write_odes_f90(fileName, speciesList, reactionList):
	nSpecies = len(speciesList)
	nReactions = len(reactionList)
	output = open(fileName, mode='w')

	# Prepare and write the electron conservation equation
    #output.write(conserve_species('e-', constituentList, codeFormat='F90'))
	output.write(electron_eq(speciesList))
    # Prepare and write the loss and formation terms for each ODE
	output.write('\n')
	#go through every species and build two strings, one with eq for all destruction routes and one for all formation
	for n,species in enumerate(speciesList):
		lossString = '' ; formString = ''
		#go through entire reaction list
		for i,reaction in enumerate(reactionList):
			
			twoBody=0 #two or more bodies in a reaction mean we multiply rate by density so need to keep track
			
			#if species appear in reactants, reaction is a destruction route      	
			if species.name in reaction.reactants:
				#easy for h2 formation
				if is_H2_formation(reaction.reactants, reaction.products):
					lossString += '-2*RATE('+str(i+1)+')*D'
					continue
				#multiply string by number of time species appears in reaction. multiple() defined below
				#so far reaction string is rate(reaction_index) indexs are all +1 for fortran array indexing
				lossString += '-'+multiple(reaction.reactants.count(species.name))+'RATE('+str(i+1)+')'
				
				#now add *Y(species_index) to string for every reactant
				for reactant in set(reaction.reactants):
					n_appearances=reaction.reactants.count(reactant)
					#every species appears at least once in its loss reaction
					#so we multiply entire loss string by Y(species_index) at end
					#thus need one less Y(species_index) per reaction
					if reactant==species.name:
						n_appearances-=1
						twoBody+=1
					if reactant =="E-":
						for appearance in range(n_appearances):
							lossString += '*Y('+str(nSpecies+1)+')'
							twoBody+=1
					else:
						#look through species list and find reactant
						for j,possibleReactants in enumerate(speciesList):
							if reactant == possibleReactants.name:
								for appearance in range(n_appearances):
									lossString += '*Y('+str(j+1)+')'
									twoBody+=1
								continue
				#now string is rate(reac_index)*Y(species_index1)*Y(species_index2) may need *D if total rate is 
				#proportional to density
				if twoBody>1 or reaction.reactants.count('FREEZE') > 0 or reaction.reactants.count('DESOH2') > 0:
						lossString += '*D'	

			#same process as above but rate is positive for reactions where species is positive
			if species.name in reaction.products:
				if is_H2_formation(reaction.reactants,reaction.products):
					#honestly H should be index 1 but lets check
					H_index=speciesList.index(next((x for x in speciesList if x.name=='H')))
					formString += '+RATE('+str(i+1)+')*Y('+str(H_index+1)+')*D'
					continue

				#multiply string by number of time species appears in reaction. multiple() defined below
				#so far reaction string is rate(reaction_index) indexs are all +1 for fortran array indexing
				formString += '+'+multiple(reaction.products.count(species.name))+'RATE('+str(i+1)+')'
				
				#now add *Y(species_index) to string for every reactant						
				for reactant in set(reaction.reactants):
					n_appearances=reaction.reactants.count(reactant)
					if reactant =="E-":
						for appearance in range(n_appearances):
							formString += '*Y('+str(nSpecies+1)+')'
							twoBody+=1
					else:
						#look through species list and find reactant
						for j,possibleReactants in enumerate(speciesList):
							if reactant == possibleReactants.name:
								for appearance in range(n_appearances):
									formString += '*Y('+str(j+1)+')'
									twoBody+=1
								continue

				#now string is rate(reac_index)*Y(species_index1)*Y(species_index2) may need *D if total rate is 
				#proportional to density
				if twoBody > 1 or reaction.reactants.count('FREEZE') > 0 or reaction.reactants.count('DESOH2') > 0:
					formString += '*D'
		if lossString != '':
			lossString = '      LOSS = '+lossString+'\n'
			lossString = truncate_line(lossString)
			output.write(lossString)
		if formString != '':
			formString = '      PROD = '+formString+'\n'
			formString = truncate_line(formString)
			output.write(formString)
		ydotString = '      YDOT('+str(n+1)+') = '
		if formString != '':
			ydotString += 'PROD'
			if lossString != '': ydotString += '+'
		if lossString != '':
			ydotString += 'Y('+str(n+1)+')*LOSS'
		ydotString += '\n'
		ydotString = truncate_line(ydotString)
		output.write(ydotString)
	output.close()    

#create a file containing length of each list of moleculetypes and then the two lists (gas and grain) of species in each type
#as  well as fraction that evaporated in each type of event
def evap_lists(filename,speciesList):
	grainlist=[];mgrainlist=[];solidList=[];monoList=[];volcList=[]
	bindEnergyList=[];enthalpyList=[]

	for i,species in enumerate(speciesList):
		if species.name[0]=='#':
			#find gas phase version of grain species. For #CO it looks for first species in list with just CO and then finds the index of that
			try:
				j=speciesList.index(next((x for x in speciesList if x.name==species.name[1:]))) 
			except:
				print "\n**************************************\nWARNING\n**************************************"
				print "{0} has no gas phase equivalent in network. Every species should at least freeze out and desorb.".format(species.name)
				print "ensure {0} is in the species list, and at least one reaction involving it exists and try again".format(species.name[1:])
				print "Alternatively, provide the name of the gas phase species you would like {0} to evaporate as".format(species.name)
				input=raw_input("type x to quit Makerates or any species name to continue\n")
				if input.lower()=="x":
					exit()
				else:
					j=speciesList.index(next((x for x in speciesList if x.name==input.upper())))					

			#plus ones as fortran and python label arrays differently
			mgrainlist.append(i+1)
			grainlist.append(j+1)
			solidList.append(species.solidFraction)
			monoList.append(species.monoFraction)
			volcList.append(species.volcFraction)
			bindEnergyList.append(species.bindener)
			enthalpyList.append(species.enthalpy)

	f = open(filename, 'wb')
	writer = csv.writer(f,delimiter=',',quotechar='|',quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
	f.write(str(len(grainlist))+'\n')
	writer.writerow(grainlist)
	writer.writerow(mgrainlist)
	writer.writerow(solidList)
	writer.writerow(monoList)
	writer.writerow(volcList)
	writer.writerow(bindEnergyList)
	writer.writerow(enthalpyList)


def electron_eq(speciesList,codeFormat='F90'):
    elec_eq=''
    nSpecies=len(speciesList)

    for n,species in enumerate(speciesList):
        if species.name[-1]=='+':
            if len(elec_eq)>0: elec_eq +='+'
            elec_eq+='Y('+str(n+1)+')'
        if species.name[-1]=='-':
            if len(elec_eq)>0: elec_eq +='-'
            elec_eq+='+Y('+str(n+1)+')'   
                 
    if len(elec_eq) > 0:
        if codeFormat == 'C':   elec_eq = '  x_e = '+elec_eq+';\n'
        if codeFormat == 'F90': elec_eq = '      Y('+str(nSpecies+1)+') = '+elec_eq+'\n'
        if codeFormat == 'F77': elec_eq = '      X(1)  = '+elec_eq+'\n'
    else:
        if codeFormat == 'C':   elec_eq = '  x_e = 0;\n'
        if codeFormat == 'F90': elec_eq = '      Y('+str(nSpecies+1)+') = 0\n'
        if codeFormat == 'F77': elec_eq = '      X(1)  = 0\n'
    if codeFormat == 'F77': elec_eq = truncate_line(elec_eq,codeFormat='F77')
    if codeFormat == 'F90': elec_eq = truncate_line(elec_eq)
    return elec_eq


# Create the appropriate multiplication string for a given number
def multiple(number):
    if number == 1: return ''
    else: return str(number)+'*'

# Truncate long lines for use in fixed-format Fortran code
def truncate_line(input, codeFormat='F90', continuationCode=None):
    lineLength = 72
    maxlines=30
    lines=0
    result = ''
    index=input.index('=')
    lhs=input[:index]
    while len(input) > lineLength:
        #introduced a counter up to max continuation lines allow, if reached a new equation is started
        lines+=1
        if lines ==maxlines:
            index = max([input.rfind('+',0,lineLength),input.rfind('-',0,lineLength)])
            result += input[:index]+'\n'
            input=lhs+'='+lhs+input[index:]
            lines=0
        else:
            index = max([input.rfind('+',0,lineLength),input.rfind('-',0,lineLength),input.rfind('*',0,lineLength),input.rfind('/',0,lineLength)])
            if codeFormat == 'F90':
                if continuationCode != None: result += input[:index]+' '+continuationCode.strip()+'\n'
                else: result += input[:index]+' &\n'
            else:
                result += input[:index]+'\n'
            if continuationCode != None:
                input = continuationCode+input[index:]
            else:
                input = '     &       '+input[index:]
            

    result += input
    return result    


def is_H2_formation(reactants, products):
    nReactants = len([species for species in reactants if species != ''])
    nProducts  = len([species for species in products  if species != ''])
    if nReactants == 2 and nProducts == 1:
        if reactants[0] == 'H' and reactants[1] == 'H' and products[0] == 'H2': return True
    if nReactants == 3 and nProducts == 2:
        if reactants[0] == 'H' and reactants[1] == 'H' and reactants[2] == '#' and products[0] == 'H2' and products[1] == '#': return True
    return False