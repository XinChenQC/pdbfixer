"""
pdbfixer.py: Fixes problems in PDB files

This is part of the OpenMM molecular simulation toolkit originating from
Simbios, the NIH National Center for Physics-Based Simulation of
Biological Structures at Stanford, funded under the NIH Roadmap for
Medical Research, grant U54 GM072970. See https://simtk.org.

Portions copyright (c) 2013-2025 Stanford University and the Authors.
Authors: Peter Eastman
Contributors:

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
THE AUTHORS, CONTRIBUTORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
from __future__ import absolute_import
from dataclasses import dataclass
from typing import Literal, Optional
__author__ = "Peter Eastman"
__version__ = "1.7"

import openmm as mm
import openmm.app as app
import openmm.unit as unit
from openmm.app.internal.pdbstructure import PdbStructure
from openmm.app.internal.pdbx.reader.PdbxReader import PdbxReader
from openmm.app.element import hydrogen, oxygen
from openmm.app.forcefield import NonbondedGenerator

# Support Cythonized functions in OpenMM 7.3
# and also implementations in older versions.
try:
    from openmm.app.internal import compiled
    matchResidue = compiled.matchResidueToTemplate
except ImportError:
    matchResidue = app.forcefield._matchResidue

import numpy as np
import numpy.linalg as lin
import sys
import os
import os.path
import math
from collections import defaultdict

if sys.version_info >= (3,0):
    from urllib.request import urlopen
    from io import StringIO
else:
    from urllib2 import urlopen
    from cStringIO import StringIO

substitutions = {
    '2AS':'ASP', '3AH':'HIS', '5HP':'GLU', '5OW':'LYS', 'ACL':'ARG', 'AGM':'ARG', 'AIB':'ALA', 'ALM':'ALA', 'ALO':'THR', 'ALY':'LYS', 'ARM':'ARG',
    'ASA':'ASP', 'ASB':'ASP', 'ASK':'ASP', 'ASL':'ASP', 'ASQ':'ASP', 'AYA':'ALA', 'BCS':'CYS', 'BHD':'ASP', 'BMT':'THR', 'BNN':'ALA',
    'BUC':'CYS', 'BUG':'LEU', 'C5C':'CYS', 'C6C':'CYS', 'CAS':'CYS', 'CCS':'CYS', 'CEA':'CYS', 'CGU':'GLU', 'CHG':'ALA', 'CLE':'LEU', 'CME':'CYS',
    'CSD':'ALA', 'CSO':'CYS', 'CSP':'CYS', 'CSS':'CYS', 'CSW':'CYS', 'CSX':'CYS', 'CXM':'MET', 'CY1':'CYS', 'CY3':'CYS', 'CYG':'CYS',
    'CYM':'CYS', 'CYQ':'CYS', 'DAH':'PHE', 'DAL':'ALA', 'DAR':'ARG', 'DAS':'ASP', 'DCY':'CYS', 'DGL':'GLU', 'DGN':'GLN', 'DHA':'ALA',
    'DHI':'HIS', 'DIL':'ILE', 'DIV':'VAL', 'DLE':'LEU', 'DLY':'LYS', 'DNP':'ALA', 'DPN':'PHE', 'DPR':'PRO', 'DSN':'SER', 'DSP':'ASP',
    'DTH':'THR', 'DTR':'TRP', 'DTY':'TYR', 'DVA':'VAL', 'EFC':'CYS', 'FLA':'ALA', 'FME':'MET', 'GGL':'GLU', 'GL3':'GLY', 'GLZ':'GLY',
    'GMA':'GLU', 'GSC':'GLY', 'HAC':'ALA', 'HAR':'ARG', 'HIC':'HIS', 'HIP':'HIS', 'HMR':'ARG', 'HPQ':'PHE', 'HTR':'TRP', 'HYP':'PRO',
    'IAS':'ASP', 'IIL':'ILE', 'IYR':'TYR', 'KCX':'LYS', 'LLP':'LYS', 'LLY':'LYS', 'LTR':'TRP', 'LYM':'LYS', 'LYZ':'LYS', 'MAA':'ALA', 'MEN':'ASN',
    'MHS':'HIS', 'MIS':'SER', 'MK8':'LEU', 'MLE':'LEU', 'MPQ':'GLY', 'MSA':'GLY', 'MSE':'MET', 'MVA':'VAL', 'NEM':'HIS', 'NEP':'HIS', 'NLE':'LEU',
    'NLN':'LEU', 'NLP':'LEU', 'NMC':'GLY', 'OAS':'SER', 'OCS':'CYS', 'OMT':'MET', 'PAQ':'TYR', 'PCA':'GLU', 'PEC':'CYS', 'PHI':'PHE',
    'PHL':'PHE', 'PR3':'CYS', 'PRR':'ALA', 'PTR':'TYR', 'PYX':'CYS', 'SAC':'SER', 'SAR':'GLY', 'SCH':'CYS', 'SCS':'CYS', 'SCY':'CYS',
    'SEL':'SER', 'SEP':'SER', 'SET':'SER', 'SHC':'CYS', 'SHR':'LYS', 'SMC':'CYS', 'SOC':'CYS', 'STY':'TYR', 'SVA':'SER', 'TIH':'ALA',
    'TPL':'TRP', 'TPO':'THR', 'TPQ':'ALA', 'TRG':'LYS', 'TRO':'TRP', 'TYB':'TYR', 'TYI':'TYR', 'TYQ':'TYR', 'TYS':'TYR', 'TYY':'TYR'
}
proteinResidues = ['ALA', 'ASN', 'CYS', 'GLU', 'HIS', 'LEU', 'MET', 'PRO', 'THR', 'TYR', 'ARG', 'ASP', 'GLN', 'GLY', 'ILE', 'LYS', 'PHE', 'SER', 'TRP', 'VAL']
rnaResidues = ['A', 'G', 'C', 'U', 'I']
dnaResidues = ['DA', 'DG', 'DC', 'DT', 'DI']

class Sequence(object):
    """Sequence holds the sequence of a chain, as specified by SEQRES records."""
    def __init__(self, chainId, residues):
        self.chainId = chainId
        self.residues = residues

class ModifiedResidue(object):
    """ModifiedResidue holds information about a modified residue, as specified by a MODRES record."""
    def __init__(self, chainId, number, residueName, standardName):
        self.chainId = chainId
        self.number = number
        self.residueName = residueName
        self.standardName = standardName

class Template:
    """Template represents a standard residue, or a nonstandard one registered with registerTemplate()."""
    def __init__(self, topology, positions, terminal=None):
        self.topology = topology
        self.positions = positions
        if terminal is None:
            terminal = [False]*topology.getNumAtoms()
        self.terminal = terminal

@dataclass
class CCDAtomDefinition:
    """
    Description of an atom in a residue from the Chemical Component Dictionary (CCD).
    """
    atomName: str
    symbol: str
    leaving: bool
    coords: mm.Vec3
    charge: int
    aromatic: bool

@dataclass
class CCDBondDefinition:
    """
    Description of a bond in a residue from the Chemical Component Dictionary (CCD).
    """
    atom1: str
    atom2: str
    order: Literal['SING', 'DOUB', 'TRIP', 'QUAD', 'AROM', 'DELO', 'PI', 'POLY']
    aromatic: bool

@dataclass
class CCDResidueDefinition:
    """
    Description of a residue from the Chemical Component Dictionary (CCD).
    """
    residueName: str
    atoms: list[CCDAtomDefinition]
    bonds: list[CCDBondDefinition]

    @classmethod
    def fromReader(cls, reader: PdbxReader) -> 'CCDResidueDefinition':
        """
        Create a CCDResidueDefinition by parsing a CCD CIF file.
        """
        data = []
        reader.read(data)
        block = data[0]

        residueName = block.getObj('chem_comp').getValue("id")

        atomData = block.getObj('chem_comp_atom')
        if atomData is None:
            # The file doesn't contain any atoms, so report that no definition is available.
            return None
        atomNameCol = atomData.getAttributeIndex('atom_id')
        symbolCol = atomData.getAttributeIndex('type_symbol')
        leavingCol = atomData.getAttributeIndex('pdbx_leaving_atom_flag')
        xCol = atomData.getAttributeIndex('pdbx_model_Cartn_x_ideal')
        yCol = atomData.getAttributeIndex('pdbx_model_Cartn_y_ideal')
        zCol = atomData.getAttributeIndex('pdbx_model_Cartn_z_ideal')
        chargeCol = atomData.getAttributeIndex('charge')
        aromaticCol = atomData.getAttributeIndex('pdbx_aromatic_flag')

        atoms = [
            CCDAtomDefinition(
                atomName=row[atomNameCol],
                symbol=row[symbolCol],
                leaving=row[leavingCol] == 'Y',
                coords=mm.Vec3(float(row[xCol]), float(row[yCol]), float(row[zCol]))*0.1,
                charge=row[chargeCol],
                aromatic=row[aromaticCol] == 'Y'
            ) for row in atomData.getRowList()
        ]

        bondData = block.getObj('chem_comp_bond')
        if bondData is not None:
            atom1Col = bondData.getAttributeIndex('atom_id_1')
            atom2Col = bondData.getAttributeIndex('atom_id_2')
            orderCol = bondData.getAttributeIndex('value_order')
            aromaticCol = bondData.getAttributeIndex('pdbx_aromatic_flag')
            bonds = [
                CCDBondDefinition(
                    atom1=row[atom1Col],
                    atom2=row[atom2Col],
                    order=row[orderCol],
                    aromatic=row[aromaticCol] == 'Y',
                ) for row in bondData.getRowList()
            ]
        else:
            bonds = []

        return cls(residueName=residueName, atoms=atoms, bonds=bonds)

def _guessFileFormat(file, filename):
    """Guess whether a file is PDB or PDBx/mmCIF based on its filename and contents."""
    filename = filename.lower()
    if '.pdbx' in filename or '.cif' in filename:
        return 'pdbx'
    if '.pdb' in filename:
        return 'pdb'
    for line in file:
        if line.startswith('data_') or line.startswith('loop_'):
            file.seek(0)
            return 'pdbx'
        if line.startswith('HEADER') or line.startswith('REMARK') or line.startswith('TITLE '):
            file.seek(0)
            return 'pdb'

    # It's certainly not a valid PDBx/mmCIF.  Guess that it's a PDB.

    file.seek(0)
    return 'pdb'

def _overlayPoints(points1, points2):
    """Given two sets of points, determine the translation and rotation that matches them as closely as possible.

    Parameters
    ----------
    points1 (numpy array of openmm.unit.Quantity with units compatible with distance) - reference set of coordinates
    points2 (numpy array of openmm.unit.Quantity with units compatible with distance) - set of coordinates to be rotated

    Returns
    -------
    translate2 - vector to translate points2 by in order to center it
    rotate - rotation matrix to apply to centered points2 to map it on to points1
    center1 - center of points1

    Notes
    -----
    This is based on W. Kabsch, Acta Cryst., A34, pp. 828-829 (1978).

    """

    if len(points1) == 0:
        return (mm.Vec3(0, 0, 0), np.identity(3), mm.Vec3(0, 0, 0))
    if len(points1) == 1:
        return (points1[0], np.identity(3), -1*points2[0])

    # Compute centroids.

    center1 = unit.sum(points1)/float(len(points1))
    center2 = unit.sum(points2)/float(len(points2))

    # Compute R matrix.

    R = np.zeros((3, 3))
    for p1, p2 in zip(points1, points2):
        x = p1-center1
        y = p2-center2
        for i in range(3):
            for j in range(3):
                R[i][j] += y[i]*x[j]

    # Use an SVD to compute the rotation matrix.

    (u, s, v) = lin.svd(R)
    return (-1*center2, np.dot(u, v).transpose(), center1)

def _dihedralRotation(points, angle):
    """Given four points that form a dihedral, compute the matrix that rotates the last point around the axis to
    produce the desired dihedral angle."""
    points = [p.value_in_unit(unit.nanometer) for p in points]
    v0 = points[0]-points[1]
    v1 = points[2]-points[1]
    v2 = points[2]-points[3]
    cp0 = np.cross(v0, v1)
    cp1 = np.cross(v1, v2)
    axis = v1/unit.norm(v1)
    currentAngle = np.arctan2(np.dot(np.cross(cp0, cp1), axis), np.dot(cp0, cp1))
    ct = np.cos(angle-currentAngle)
    st = np.sin(angle-currentAngle)
    return np.array([
        [axis[0]*axis[0]*(1-ct) + ct,            axis[0]*axis[1]*(1-ct) - axis[2]*st,    axis[0]*axis[2]*(1-ct) + axis[1]*st],
        [axis[1]*axis[0]*(1-ct) + axis[2]*st,    axis[1]*axis[1]*(1-ct) + ct,            axis[1]*axis[2]*(1-ct) - axis[0]*st],
        [axis[2]*axis[0]*(1-ct) - axis[1]*st,    axis[2]*axis[1]*(1-ct) + axis[0]*st,    axis[2]*axis[2]*(1-ct) + ct        ]
    ])

def _findUnoccupiedDirection(point, positions):
    """Given a point in space and a list of atom positions, find the direction in which the local density of atoms is lowest."""

    point = point.value_in_unit(unit.nanometers)
    direction = mm.Vec3(0, 0, 0)
    for pos in positions.value_in_unit(unit.nanometers):
        delta = pos-point
        distance = unit.norm(delta)
        if distance > 0.1:
            distance2 = distance*distance
            direction -= delta/(distance2*distance2)
    direction /= unit.norm(direction)
    return direction

class PDBFixer(object):
    """PDBFixer implements many tools for fixing problems in PDB and PDBx/mmCIF files.
    """

    def __init__(self, filename=None, pdbfile=None, pdbxfile=None, url=None, pdbid=None, platform=None):
        """Create a new PDBFixer instance to fix problems in a PDB or PDBx/mmCIF file.

        Parameters
        ----------
        filename : str, optional, default=None
            The name of the file to read.  The format is determined automatically based on the filename extension, or if
            that is ambiguous, by looking at the file content.
        pdbfile : file, optional, default=None
            A file-like object from which the PDB file is to be read.
            The file is not closed after reading.
        pdbxfile : file, optional, default=None
            A file-like object from which the PDBx/mmCIF file is to be read.
            The file is not closed after reading.
        url : str, optional, default=None
            A URL specifying the internet location from which the file contents should be retrieved.  The format is
            determined automatically by looking for a filename extension in the URL, or if that is ambiguous, by looking
            at the file content.
        pdbid : str, optional, default=None
            A four-letter PDB code specifying the structure to be retrieved from the RCSB.
        platform: openmm.Platform, optional, default=None
            The Platform to use for running calculations.  If None, a Platform will be chosen automatically.

        Notes
        -----
        Only one of structure, filename, pdbfile, pdbxfile, url, or pdbid may be specified or an exception will be thrown.

        Examples
        --------

        Start from a filename.

        >>> filename = 'tests/data/test.pdb'
        >>> fixer = PDBFixer(filename=filename)

        Start from a file object.

        >>> with open(filename) as f:
        ...     fixer = PDBFixer(pdbfile=f)

        Start from a URL.

        >>> fixer = PDBFixer(url='http://www.rcsb.org/pdb/files/1VII.pdb')

        Start from a PDB code.

        >>> fixer = PDBFixer(pdbid='1VII')

        """

        # Check to make sure only one option has been specified.
        if bool(filename) + bool(pdbfile) + bool(pdbxfile) + bool(url) + bool(pdbid) != 1:
            raise Exception("Exactly one option [filename, pdbfile, pdbxfile, url, pdbid] must be specified.")

        self.platform = platform
        self.source = None
        if pdbid:
            # A PDB id has been specified.
            url = 'http://www.rcsb.org/pdb/files/%s.pdb' % pdbid
        if filename:
            # A local file has been specified.
            self.source = filename
            file = open(filename, 'r')
            if _guessFileFormat(file, filename) == 'pdbx':
                self._initializeFromPDBx(file)
            else:
                self._initializeFromPDB(file)
            file.close()
        elif pdbfile:
            # A file-like object has been specified.
            self._initializeFromPDB(pdbfile)
        elif pdbxfile:
            # A file-like object has been specified.
            self._initializeFromPDBx(pdbxfile)
        elif url:
            # A URL has been specified.
            self.source = url
            file = urlopen(url)
            contents = file.read().decode('utf-8')
            file.close()
            file = StringIO(contents)
            if _guessFileFormat(file, url) == 'pdbx':
                self._initializeFromPDBx(contents)
            else:
                self._initializeFromPDB(StringIO(contents))

        # Check the structure has some atoms in it.
        atoms = list(self.topology.atoms())
        if len(atoms) == 0:
            raise Exception("Structure contains no atoms.")

        # Keep a cache of downloaded CCD definitions
        self._ccdCache = {}

        # Load the templates.

        self.templates = {}
        self._standardTemplates = set()
        templatesPath = os.path.join(os.path.dirname(__file__), 'templates')
        for file in os.listdir(templatesPath):
            templatePdb = app.PDBFile(os.path.join(templatesPath, file))
            name = next(templatePdb.topology.residues()).name
            self.templates[name] = Template(templatePdb.topology, templatePdb.positions)
            self._standardTemplates.add(name)

    def _initializeFromPDB(self, file):
        """Initialize this object by reading a PDB file."""

        structure = PdbStructure(file)
        pdb = app.PDBFile(structure)
        self.topology = pdb.topology
        self.positions = pdb.positions
        self.sequences = [Sequence(s.chain_id, s.residues) for s in structure.sequences]
        self.modifiedResidues = [ModifiedResidue(r.chain_id, r.number, r.residue_name, r.standard_name) for r in structure.modified_residues]

    def _initializeFromPDBx(self, file):
        """Initialize this object by reading a PDBx/mmCIF file."""

        pdbx = app.PDBxFile(file)
        self.topology = pdbx.topology
        self.positions = pdbx.positions

        # PDBxFile doesn't record the information about sequence or modified residues, so we need to read them separately.

        file.seek(0)
        reader = PdbxReader(file)
        data = []
        reader.read(data)
        block = data[0]

        # Load the sequence data.

        sequenceData = block.getObj('entity_poly_seq')
        sequences = {}
        if sequenceData is not None:
            entityIdCol = sequenceData.getAttributeIndex('entity_id')
            residueCol = sequenceData.getAttributeIndex('mon_id')
            for row in sequenceData.getRowList():
                entityId = row[entityIdCol]
                residue = row[residueCol]
                if entityId not in sequences:
                    sequences[entityId] = []
                sequences[entityId].append(residue)

        # Sequences are stored by "entity".  There could be multiple chains that are all the same entity, so we need to
        # convert from entities to chains.

        asymData = block.getObj('struct_asym')
        self.sequences = []
        if asymData is not None:
            asymIdCol = asymData.getAttributeIndex('id')
            entityIdCol = asymData.getAttributeIndex('entity_id')
            for row in asymData.getRowList():
                asymId = row[asymIdCol]
                entityId = row[entityIdCol]
                if entityId in sequences:
                    self.sequences.append(Sequence(asymId, sequences[entityId]))

        # Load the modified residues.

        modData = block.getObj('pdbx_struct_mod_residue')
        self.modifiedResidues = []
        if modData is not None:
            asymIdCol = modData.getAttributeIndex('label_asym_id')
            resNameCol = modData.getAttributeIndex('label_comp_id')
            resNumCol = modData.getAttributeIndex('auth_seq_id')
            standardResCol = modData.getAttributeIndex('parent_comp_id')
            if -1 not in (asymIdCol, resNameCol, resNumCol, standardResCol):
                for row in modData.getRowList():
                    self.modifiedResidues.append(ModifiedResidue(row[asymIdCol], int(row[resNumCol]), row[resNameCol], row[standardResCol]))


    def _downloadCCDDefinition(self, residueName: str) -> Optional[CCDResidueDefinition]:
        """
        Download a residue definition from the Chemical Component Dictionary.

        This method caches results in the ``PDBFixer`` object.

        Parameters
        ----------
        residueName : str
            The name of the residue, as specified in the PDB Chemical Component
            Dictionary.

        Returns
        -------
        None
            If the residue could not be downloaded.
        ccdDefinition : CCDResidueDefinition
            The CCD definition for the requested residue.
        """
        residueName = residueName.upper()

        if residueName in self._ccdCache:
            return self._ccdCache[residueName]

        try:
            file = urlopen(f'https://files.rcsb.org/ligands/download/{residueName}.cif')
            contents = file.read().decode('utf-8')
            file.close()
        except:
            # None represents that the residue has been looked up and could not
            # be found. This is distinct from an entry simply not being present
            # in the cache.
            self._ccdCache[residueName] = None
            return None

        reader = PdbxReader(StringIO(contents))
        ccdDefinition = CCDResidueDefinition.fromReader(reader)
        self._ccdCache[residueName] = ccdDefinition
        return ccdDefinition

    def _getTemplate(self, name):
        """Return the template with a name.  If none has been registered, this will return None."""
        if name in self.templates:
            return self.templates[name]
        return None

    def registerTemplate(self, topology, positions, terminal=None):
        """Register a template for a nonstandard residue.  This allows PDBFixer to add missing residues of this type,
        to add missing atoms to existing residues, and to mutate other residues to it.
        Parameters
        ----------
        topology: openmm.app.Topology
            A Topology containing a single chain with a single residue, describing the nonstandard residue
            being registered.
        positions: array of shape (n_atoms, 3)
            The positions of the atoms in the residue in a typical conformation.  These positions are used
            when adding missing atoms or residues.
        terminal: optional list of bool
            If this is present, it should be a list of length equal to the number of atoms in the residue.
            If an element is True, that indicates the corresponding atom should only be added to terminal
            residues.
        """
        residues = list(topology.residues())
        if len(residues) != 1:
            raise ValueError('The Topology must contain a single residue')
        if topology.getNumAtoms() != len(positions):
            raise ValueError('The number of positions does not match the number of atoms in the Topology')
        if terminal is not None and len(terminal) != topology.getNumAtoms():
            raise ValueError('The number of terminal flags does not match the number of atoms in the Topology')
        self.templates[residues[0].name] = Template(topology, positions, terminal)

    def downloadTemplate(self, name):
        """Attempt to download a residue definition from the PDB and register a template for it.

        Parameters
        ----------
        name: str
            The name of the residue, as specified in the PDB Chemical Component Dictionary.

        Returns
        -------
        True if a template was successfully registered, false otherwise.
        """
        name = name.upper()

        ccdDefinition = self._downloadCCDDefinition(name)
        if ccdDefinition is None:
            return False

        # Load the atoms.
        topology = app.Topology()
        chain = topology.addChain()
        residue = topology.addResidue(name, chain)
        positions = []
        atomByName = {}
        terminal = []
        for atomDefinition in ccdDefinition.atoms:
            atomName = atomDefinition.atomName
            atom = topology.addAtom(atomName, app.Element.getBySymbol(atomDefinition.symbol), residue)
            atomByName[atomName] = atom
            terminal.append(atomDefinition.leaving)
            positions.append(atomDefinition.coords)
        positions = positions*unit.nanometers

        # Load the bonds.
        for bondDefinition in ccdDefinition.bonds:
            topology.addBond(atomByName[bondDefinition.atom1], atomByName[bondDefinition.atom2])

        self.registerTemplate(topology, positions, terminal)
        return True

    def _addAtomsToTopology(self, heavyAtomsOnly, omitUnknownMolecules):
        """Create a new Topology in which missing atoms have been added.

        Parameters
        ----------
        heavyAtomsOnly : bool
            If True, only heavy atoms will be added to the topology.
        omitUnknownMolecules : bool
            If True, unknown molecules will be omitted from the topology.

        Returns
        -------
        newTopology : openmm.app.Topology
            A new Topology object containing atoms from the old.
        newPositions : list of openmm.unit.Quantity with units compatible with nanometers
            Atom positions for the new Topology object.
        newAtoms : openmm.app.Topology.Atom
            New atom objects.
        existingAtomMap : dict
            Mapping from old atoms to new atoms.

        """

        newTopology = app.Topology()
        newPositions = []*unit.nanometer
        newAtoms = []
        existingAtomMap = {}
        addedAtomMap = {}
        addedHeterogenBonds = []
        residueCenters = [self._computeResidueCenter(res).value_in_unit(unit.nanometers) for res in self.topology.residues()]*unit.nanometers
        for chain in self.topology.chains():
            if omitUnknownMolecules and all(self._getTemplate(residue.name) is None for residue in chain.residues()):
                continue
            chainResidues = list(chain.residues())
            newChain = newTopology.addChain(chain.id)
            for indexInChain, residue in enumerate(chain.residues()):

                # Insert missing residues here.

                if (chain.index, indexInChain) in self.missingResidues:
                    insertHere = self.missingResidues[(chain.index, indexInChain)]
                    endPosition = self._computeResidueCenter(residue)
                    if indexInChain > 0:
                        startPosition = self._computeResidueCenter(chainResidues[indexInChain-1])
                        loopDirection = _findUnoccupiedDirection((startPosition+endPosition)/2, residueCenters)
                    else:
                        outward = _findUnoccupiedDirection(endPosition, residueCenters)*unit.nanometers
                        norm = unit.norm(outward)
                        if norm > 0*unit.nanometer:
                            outward *= len(insertHere)*0.5*unit.nanometer/norm
                        startPosition = endPosition+outward
                        loopDirection = None
                    firstIndex = int(residue.id)-len(insertHere)
                    self._addMissingResiduesToChain(newChain, insertHere, startPosition, endPosition, loopDirection, residue, newAtoms, newPositions, firstIndex)

                # Create the new residue and add existing heavy atoms.

                newResidue = newTopology.addResidue(residue.name, newChain, residue.id, residue.insertionCode)
                for atom in residue.atoms():
                    if not heavyAtomsOnly or (atom.element is not None and atom.element != hydrogen):
                        if atom.name == 'OXT' and (chain.index, indexInChain+1) in self.missingResidues:
                            continue # Remove terminal oxygen, since we'll add more residues after this one
                        newAtom = newTopology.addAtom(atom.name, atom.element, newResidue)
                        existingAtomMap[atom] = newAtom
                        newPositions.append(self.positions[atom.index])
                if residue in self.missingAtoms:

                    # Find corresponding atoms in the residue and the template.

                    template = self._getTemplate(residue.name)
                    atomPositions = dict((atom.name, self.positions[atom.index]) for atom in residue.atoms())
                    points1 = []
                    points2 = []
                    for atom in template.topology.atoms():
                        if atom.name in atomPositions:
                            points1.append(atomPositions[atom.name].value_in_unit(unit.nanometer))
                            points2.append(template.positions[atom.index].value_in_unit(unit.nanometer))

                    # Compute the optimal transform to overlay them.

                    (translate2, rotate, translate1) = _overlayPoints(points1, points2)

                    # Add the missing atoms.

                    addedAtomMap[residue] = {}
                    for atom in self.missingAtoms[residue]:
                        newAtom = newTopology.addAtom(atom.name, atom.element, newResidue)
                        newAtoms.append(newAtom)
                        addedAtomMap[residue][atom] = newAtom
                        templatePosition = template.positions[atom.index].value_in_unit(unit.nanometer)
                        newPositions.append((mm.Vec3(*np.dot(rotate, templatePosition+translate2))+translate1)*unit.nanometer)

                    if residue.name not in app.Topology._standardBonds:

                        # This is a heterogen.  Make sure bonds will get added for any new atoms.

                        addedAtomNames = set(atom.name for atom in addedAtomMap[residue])
                        newResidueAtoms = {atom.name: atom for atom in newResidue.atoms()}
                        for atom1, atom2 in template.topology.bonds():
                            if atom1.name in addedAtomNames or atom2.name in addedAtomNames:
                                if atom1.name in newResidueAtoms and atom2.name in newResidueAtoms:
                                    addedHeterogenBonds.append((newResidueAtoms[atom1.name], newResidueAtoms[atom2.name]))

                if residue in self.missingTerminals:
                    terminalsToAdd = self.missingTerminals[residue]
                else:
                    terminalsToAdd = None

                # If this is the end of the chain, add any missing residues that come after it.

                if residue == chainResidues[-1] and (chain.index, indexInChain+1) in self.missingResidues:
                    insertHere = self.missingResidues[(chain.index, indexInChain+1)]
                    if len(insertHere) > 0:
                        startPosition = self._computeResidueCenter(residue)
                        outward = _findUnoccupiedDirection(startPosition, residueCenters)*unit.nanometers
                        norm = unit.norm(outward)
                        if norm > 0*unit.nanometer:
                            outward *= len(insertHere)*0.5*unit.nanometer/norm
                        endPosition = startPosition+outward
                        firstIndex = int(residue.id)+1
                        self._addMissingResiduesToChain(newChain, insertHere, startPosition, endPosition, None, residue, newAtoms, newPositions, firstIndex)
                        newResidue = list(newChain.residues())[-1]
                        if newResidue.name in proteinResidues:
                            terminalsToAdd = ['OXT']
                        else:
                            terminalsToAdd = None

                # If a terminal OXT is missing, add it.

                if terminalsToAdd is not None:
                    atomPositions = dict((atom.name, newPositions[atom.index].value_in_unit(unit.nanometer)) for atom in newResidue.atoms())
                    if 'OXT' in terminalsToAdd:
                        newAtom = newTopology.addAtom('OXT', oxygen, newResidue)
                        newAtoms.append(newAtom)
                        d_ca_o = atomPositions['O']-atomPositions['CA']
                        d_ca_c = atomPositions['C']-atomPositions['CA']
                        d_ca_c /= unit.sqrt(unit.dot(d_ca_c, d_ca_c))
                        v = d_ca_o - d_ca_c*unit.dot(d_ca_c, d_ca_o)
                        newPositions.append((atomPositions['O']+2*v)*unit.nanometer)
        newTopology.setUnitCellDimensions(self.topology.getUnitCellDimensions())
        newTopology.createStandardBonds()
        newTopology.createDisulfideBonds(newPositions)

        # Add the existing bonds between atoms in heterogens.

        for a1,a2 in self.topology.bonds():
            if a1 in existingAtomMap and a2 in existingAtomMap and (a1.residue.name not in app.Topology._standardBonds or a2.residue.name not in app.Topology._standardBonds):
                newTopology.addBond(existingAtomMap[a1], existingAtomMap[a2])

        # Add any new bonds within heterogens.

        bonds = set((atom1.index, atom2.index) for atom1, atom2 in newTopology.bonds())
        for atom1, atom2 in addedHeterogenBonds:
            if (atom1.index, atom2.index) not in bonds and (atom2.index, atom1.index) not in bonds:
                newTopology.addBond(atom1, atom2)
                bonds.add((atom1.index, atom2.index))

        # Return the results.

        return (newTopology, newPositions, newAtoms, existingAtomMap)

    def _computeResidueCenter(self, residue):
        """Compute the centroid of a residue."""
        return unit.sum([self.positions[atom.index] for atom in residue.atoms()])/len(list(residue.atoms()))

    def _addMissingResiduesToChain(self, chain, residueNames, startPosition, endPosition, loopDirection, orientTo, newAtoms, newPositions, firstIndex):
        """Add a series of residues to a chain."""
        orientToPositions = dict((atom.name, self.positions[atom.index]) for atom in orientTo.atoms())
        if loopDirection is None:
            loopDirection = mm.Vec3(0, 0, 0)

        # We'll add the residues in an arc connecting the endpoints.  Figure out the height of that arc.

        length = unit.norm(endPosition-startPosition)
        numResidues = len(residueNames)
        if length > numResidues*0.3*unit.nanometers:
            loopHeight = 0*unit.nanometers
        else:
            loopHeight = (numResidues*0.3*unit.nanometers-length)/2

        # Add the residues.

        try:
            prevResidue = list(chain.residues())[-1]
        except:
            prevResidue = None
        for i, residueName in enumerate(residueNames):
            template = self._getTemplate(residueName)

            # Find a translation that best matches the adjacent residue.

            points1 = []
            points2 = []
            for atom in template.topology.atoms():
                if atom.name in orientToPositions:
                    points1.append(orientToPositions[atom.name].value_in_unit(unit.nanometer))
                    points2.append(template.positions[atom.index].value_in_unit(unit.nanometer))
            (translate2, rotate, translate1) = _overlayPoints(points1, points2)

            # Create the new residue.

            newResidue = chain.topology.addResidue(residueName, chain, "%d" % ((firstIndex+i)%10000))
            fraction = (i+1.0)/(numResidues+1.0)
            translate = startPosition + (endPosition-startPosition)*fraction + loopHeight*math.sin(fraction*math.pi)*loopDirection
            templateAtoms = list(template.topology.atoms())
            if newResidue == next(chain.residues()):
                templateAtoms = [atom for atom in templateAtoms if atom.name not in ('P', 'OP1', 'OP2')]
            for atom in templateAtoms:
                newAtom = chain.topology.addAtom(atom.name, atom.element, newResidue)
                newAtoms.append(newAtom)
                templatePosition = template.positions[atom.index].value_in_unit(unit.nanometer)
                newPositions.append(mm.Vec3(*np.dot(rotate, templatePosition))*unit.nanometer+translate)
            if prevResidue is not None:
                atoms1 = {atom.name: atom for atom in prevResidue.atoms()}
                atoms2 = {atom.name: atom for atom in newResidue.atoms()}
                if 'CA' in atoms1 and 'C' in atoms1 and 'N' in atoms2 and 'CA' in atoms2:

                    # We're adding a peptide bond between this residue and the previous one.  Rotate it to try to
                    # put the peptide bond into the trans conformation.

                    atoms = (atoms1['CA'], atoms1['C'], atoms2['N'], atoms2['CA'])
                    points = [newPositions[a.index] for a in atoms]
                    rotation = _dihedralRotation(points, np.pi)
                    for atom in newResidue.atoms():
                        d = (newPositions[atom.index]-points[2]).value_in_unit(unit.nanometer)
                        newPositions[atom.index] = mm.Vec3(*np.dot(rotation, d))*unit.nanometer + points[2]

            prevResidue = newResidue

    def _renameNewChains(self, startIndex):
        """Rename newly added chains to conform with existing naming conventions.

        Parameters
        ----------
        startIndex : int
            The index of the first new chain in self.topology.chains().
        """
        # If all chains are new, nothing to do
        if startIndex == 0:
            return

        # If the last chain ID was originally a letter, continue alphabetically until reaching Z
        chains = list(self.topology.chains())
        for newChainIndex in range(startIndex, len(chains)):
            prevChainId = chains[newChainIndex - 1].id
            if len(prevChainId) == 1 and "A" <= prevChainId < "Z":
                chains[newChainIndex].id = chr(ord(prevChainId) + 1)

    def removeChains(self, chainIndices=None, chainIds=None):
        """Remove a set of chains from the structure.

        Parameters
        ----------
        chainIndices : list of int, optional, default=None
            List of indices of chains to remove.
        chainIds : list of str, optional, default=None
            List of chain ids of chains to remove.

        Examples
        --------

        Load a PDB file with two chains and eliminate the second chain.

        >>> fixer = PDBFixer(pdbid='4J7F')
        >>> fixer.removeChains(chainIndices=[1])

        Load a PDB file with two chains and eliminate chains named 'B' and 'D'.

        >>> fixer = PDBFixer(pdbid='4J7F')
        >>> fixer.removeChains(chainIds=['B','D'])

        """
        modeller = app.Modeller(self.topology, self.positions)
        allChains = list(self.topology.chains())

        if chainIndices == None:
            chainIndices = list()
        if chainIds != None:
            # Add all chains that match the selection to the list.
            for (chainNumber, chain) in enumerate(allChains):
                if chain.id in chainIds:
                    chainIndices.append(chainNumber)
            # Ensure only unique entries remain.
            chainIndices = list(set(chainIndices))

        # Do nothing if no chains will be deleted.
        if len(chainIndices) == 0:
            return

        modeller.delete(allChains[i] for i in chainIndices)
        self.topology = modeller.topology
        self.positions = modeller.positions

        return

    def findMissingResidues(self):
        """Find residues that are missing from the structure.

        The results are stored into the missingResidues field, which is a dict.  Each key is a tuple consisting of
        the index of a chain, and the residue index within that chain at which new residues should be inserted.
        The corresponding value is a list of the names of residues to insert there.

        Examples
        --------

        >>> fixer = PDBFixer(pdbid='1VII')
        >>> fixer.findMissingResidues()
        >>> missing_residues = fixer.missingResidues

        """
        chains = [c for c in self.topology.chains() if len(list(c.residues())) > 0]
        chainWithGaps = {}

        # Find the sequence of each chain, with gaps for missing residues.

        for chain in chains:
            residues = list(chain.residues())
            ids = [int(r.id) for r in residues]
            for i, res in enumerate(residues):
                if res.insertionCode not in ('', ' '):
                    for j in range(i, len(residues)):
                        ids[j] += 1
            minResidue = min(ids)
            maxResidue = max(ids)
            chainWithGaps[chain] = [None]*(maxResidue-minResidue+1)
            for r, id in zip(residues, ids):
                chainWithGaps[chain][id-minResidue] = r.name

        # Try to find the chain that matches each sequence.

        chainSequence = {}
        chainOffset = {}
        for sequence in self.sequences:
            for chain in chains:
                if chain.id != sequence.chainId:
                    continue
                if chain in chainSequence:
                    continue
                for offset in range(len(sequence.residues)-len(chainWithGaps[chain])+1):
                    if all(a == b or b == None for a,b in zip(sequence.residues[offset:], chainWithGaps[chain])):
                        chainSequence[chain] = sequence
                        chainOffset[chain] = offset
                        break
                if chain in chainSequence:
                    break

        # Now build the list of residues to add.

        self.missingResidues = {}
        for chain in self.topology.chains():
            if chain in chainSequence:
                offset = chainOffset[chain]
                sequence = chainSequence[chain].residues
                gappedSequence = chainWithGaps[chain]
                index = 0
                for i in range(len(sequence)):
                    if i < offset or i >= len(gappedSequence)+offset or gappedSequence[i-offset] is None:
                        key = (chain.index, index)
                        if key not in self.missingResidues:
                            self.missingResidues[key] = []
                        residueName = sequence[i]
                        if residueName in substitutions:
                            residueName = substitutions[sequence[i]]
                        self.missingResidues[key].append(residueName)
                    else:
                        index += 1

    def findNonstandardResidues(self):
        """Identify non-standard residues found in the structure, and select standard residues to replace them with.

        The results are stored into the nonstandardResidues field, which is a map of Residue objects to the names
        of suggested replacement residues.

        Examples
        --------

        Find nonstandard residues.

        >>> fixer = PDBFixer(pdbid='1YRI')
        >>> fixer.findNonstandardResidues()
        >>> nonstandard_residues = fixer.nonstandardResidues

        """

        # First find residues based on our table of standard substitutions.

        nonstandard = dict((r, substitutions[r.name]) for r in self.topology.residues() if r.name in substitutions)

        # Now add ones based on MODRES records.

        modres = dict(((m.chainId, str(m.number), m.residueName), m.standardName) for m in self.modifiedResidues)
        for chain in self.topology.chains():
            for residue in chain.residues():
                key = (chain.id, residue.id, residue.name)
                if key in modres:
                    replacement = modres[key]
                    if replacement == 'DU':
                        replacement = 'DT'
                    if self._getTemplate(replacement) != None:
                        nonstandard[residue] = replacement
        self.nonstandardResidues = [(r, nonstandard[r]) for r in sorted(nonstandard, key=lambda r: r.index)]

    def replaceNonstandardResidues(self):
        """Replace every residue listed in the nonstandardResidues field with the specified standard residue.

        Notes
        -----
        You must have first called findNonstandardResidues() to identify nonstandard residues.

        Examples
        --------

        Find and replace nonstandard residues using replacement templates stored in the 'templates' field of PDBFixer object.

        >>> fixer = PDBFixer(pdbid='1YRI')
        >>> fixer.findNonstandardResidues()
        >>> fixer.replaceNonstandardResidues()

        """
        if len(self.nonstandardResidues) > 0:
            deleteAtoms = []

            # Find atoms that should be deleted.

            for residue, replaceWith in self.nonstandardResidues:
                residue.name = replaceWith
                template = self._getTemplate(replaceWith)
                standardAtoms = set(atom.name for atom in template.topology.atoms())
                for atom in residue.atoms():
                    if atom.element in (None, hydrogen) or atom.name not in standardAtoms:
                        deleteAtoms.append(atom)

            # Delete them.

            modeller = app.Modeller(self.topology, self.positions)
            modeller.delete(deleteAtoms)
            self.topology = modeller.topology
            self.positions = modeller.positions


    def applyMutations(self, mutations, chain_id):
        """Apply a list of amino acid substitutions to make a mutant protein.

        Parameters
        ----------
        mutations : list of strings
            Each string must include the resName (original), index,
            and resName (target).  For example, ALA-133-GLY will mutate
            alanine 133 to glycine.
        chain_id : str
            String based chain ID of the single chain you wish to mutate.

        Notes
        -----

        If a target residue is not a standard amino acid, and if no template
        has been registered for it with registerTemplate(), this function
        attempts to look it up from the PDB and create a new template for it.

        We require three letter codes to avoid possible ambiguitities.
        We can't guarantee that the resulting model is a good one; for
        significant changes in sequence, you should probably be using
        a standalone homology modelling tool.

        Examples
        --------

        Find nonstandard residues.

        >>> fixer = PDBFixer(pdbid='1VII')
        >>> fixer.applyMutations(["ALA-57-GLY"], "A")
        >>> fixer.findMissingResidues()
        >>> fixer.findMissingAtoms()
        >>> fixer.addMissingAtoms()
        >>> fixer.addMissingHydrogens(7.0)

        """
        # Retrieve all residues that match the specified chain_id.
        # NOTE: Multiple chains may have the same chainid, but must have unique resSeq entries.
        resSeq_to_residue = dict() # resSeq_to_residue[resid] is the residue in the requested chain corresponding to residue identifier 'resid'
        for chain in self.topology.chains():
            if chain.id == chain_id:
                for residue in chain.residues():
                    resSeq_to_residue[int(residue.id)] = residue

        # Make a map of residues to mutate based on requested mutation list.
        residue_map = dict() # residue_map[residue] is the name of the new residue to mutate to, if a mutation is desired
        for mut_str in mutations:
            old_name, resSeq, new_name = mut_str.split("-")
            resSeq = int(resSeq)

            if resSeq not in resSeq_to_residue:
                raise(KeyError("Cannot find chain %s residue %d in system!" % (chain_id, resSeq)))

            residue = resSeq_to_residue[resSeq] # retrieve the requested residue

            if residue.name != old_name:
                raise(ValueError("You asked to mutate chain %s residue %d name %s, but that residue is actually %s!" % (chain_id, resSeq, old_name, residue.name)))

            if self._getTemplate(new_name) is None:
                # Try to download a template from the PDB.
                self.downloadTemplate(new_name)
                if self._getTemplate(new_name) is None:
                    raise(KeyError("Cannot find residue %s in template library!" % new_name))

            # Store mutation
            residue_map[residue] = new_name

        # If there are mutations to be made, make them.
        if len(residue_map) > 0:
            deleteAtoms = [] # list of atoms to delete

            # Find atoms that should be deleted.
            for residue in residue_map.keys():
                replaceWith = residue_map[residue]
                residue.name = replaceWith
                template = self._getTemplate(replaceWith)
                standardAtoms = set(atom.name for atom in template.topology.atoms())
                for atom in residue.atoms():
                    if atom.element in (None, hydrogen) or atom.name not in standardAtoms:
                        deleteAtoms.append(atom)

            # Delete atoms queued to be deleted.
            modeller = app.Modeller(self.topology, self.positions)
            modeller.delete(deleteAtoms)
            self.topology = modeller.topology
            self.positions = modeller.positions


    def findMissingAtoms(self):
        """Find heavy atoms that are missing from the structure.

        The results are stored into two fields: missingAtoms and missingTerminals.  Each of these is a dict whose keys
        are Residue objects and whose values are lists of atom names.  missingAtoms contains standard atoms that should
        be present in any residue of that type.  missingTerminals contains terminal atoms that should be present at the
        start or end of a chain.

        Notes
        -----
        You must have first called findMissingResidues().

        Examples
        --------

        Find missing heavy atoms in Abl kinase structure.

        >>> fixer = PDBFixer(pdbid='2F4J')
        >>> fixer.findMissingResidues()
        >>> fixer.findMissingAtoms()
        >>> # Retrieve missing atoms.
        >>> missingAtoms = fixer.missingAtoms
        >>> # Retrieve missing terminal atoms.
        >>> missingTerminals = fixer.missingTerminals

        """
        missingAtoms = {}
        missingTerminals = {}

        # Determine which atoms have an external bond to another residue.

        hasExternal = defaultdict(bool)
        for atom1, atom2 in self.topology.bonds():
            if atom1.residue != atom2.residue:
                hasExternal[(atom1.residue, atom1.name)] = True
                hasExternal[(atom2.residue, atom2.name)] = True
        for chain in self.topology.chains():
            chainResidues = list(chain.residues())
            for residue in chain.residues():
                atomNames = [atom.name for atom in residue.atoms()]
                if all(name in atomNames for name in ['C', 'O', 'CA']):
                    # We'll be adding peptide bonds.
                    if residue != chainResidues[0]:
                        hasExternal[(residue, 'N')] = True
                    if residue != chainResidues[-1]:
                        hasExternal[(residue, 'C')] = True

        # Loop over residues.

        for chain in self.topology.chains():
            nucleic = any(res.name in dnaResidues or res.name in rnaResidues for res in chain.residues())
            chainResidues = list(chain.residues())
            for residue in chain.residues():
                template = self._getTemplate(residue.name)
                if template is not None:
                    # If an atom is marked as terminal only, and if it is bonded to any atom that has an external bond
                    # to another residue, we need to omit that atom and any other terminal-only atom bonded to it.

                    bondedTo = defaultdict(set)
                    for atom1, atom2 in template.topology.bonds():
                        bondedTo[atom1].add(atom2)
                        bondedTo[atom2].add(atom1)
                    skip = set()
                    for atom, terminal in zip(template.topology.atoms(), template.terminal):
                        if terminal:
                            for atom2 in bondedTo[atom]:
                                if hasExternal[(residue, atom2.name)]:
                                    skip.add(atom)
                    for atom, terminal in zip(template.topology.atoms(), template.terminal):
                        if terminal:
                            for atom2 in bondedTo[atom]:
                                if atom2 in skip:
                                    skip.add(atom)
                    atomNames = set(atom.name for atom in residue.atoms())
                    templateAtoms = [atom for atom in template.topology.atoms() if atom not in skip]
                    if nucleic and residue == chainResidues[0] and (chain.index, 0) not in self.missingResidues:
                        templateAtoms = [atom for atom in templateAtoms if atom.name not in ('P', 'OP1', 'OP2')]

                    # Add atoms from the template that are missing.

                    missing = []
                    for atom in templateAtoms:
                        if atom.name not in atomNames and atom.element != app.element.hydrogen:
                            missing.append(atom)
                    if len(missing) > 0:
                        missingAtoms[residue] = missing

                    # Add missing terminal atoms.

                    terminals = []
                    if residue == chainResidues[-1] and (chain.index, len(chainResidues)) not in self.missingResidues:
                        templateNames = set(atom.name for atom in template.topology.atoms())
                        if 'OXT' not in atomNames and all(name in templateNames for name in ['C', 'O', 'CA']):
                            terminals.append('OXT')
                        if len(terminals) > 0:
                            missingTerminals[residue] = terminals
        self.missingAtoms = missingAtoms
        self.missingTerminals = missingTerminals

    def addMissingAtoms(self, seed=None):
        """Add all missing heavy atoms, as specified by the missingAtoms, missingTerminals, and missingResidues fields.

        Parameters
        ----------
        seed : int
            Integer to set the random seed number of the integrator used in the minimization of the
            coordinates of the newly-added atoms.

        Notes
        -----
        You must already have called findMissingAtoms() to have identified atoms to be added.

        Examples
        --------

        Find missing heavy atoms in Abl kinase structure.

        >>> fixer = PDBFixer(pdbid='2F4J')
        >>> fixer.findMissingResidues()
        >>> fixer.findMissingAtoms()
        >>> fixer.addMissingAtoms()

        """

        # Create a Topology that 1) adds missing atoms, 2) removes all hydrogens, and 3) removes unknown molecules.

        (newTopology, newPositions, newAtoms, existingAtomMap) = self._addAtomsToTopology(True, True)
        if len(newAtoms) == 0:

            # No atoms were added, but new bonds might have been created.

            newBonds = set(newTopology.bonds())
            for atom1, atom2 in self.topology.bonds():
                if atom1 in existingAtomMap and atom2 in existingAtomMap:
                    a1 = existingAtomMap[atom1]
                    a2 = existingAtomMap[atom2]
                    if (a1, a2) in newBonds:
                        newBonds.remove((a1, a2))
                    elif (a2, a1) in newBonds:
                        newBonds.remove((a2, a1))

            # Add the new bonds to the original Topology.

            inverseAtomMap = dict((y,x) for (x,y) in existingAtomMap.items())
            for atom1, atom2 in newBonds:
                self.topology.addBond(inverseAtomMap[atom1], inverseAtomMap[atom2])
        else:

            # Create a System for energy minimizing it.

            forcefield = self._createForceField(newTopology, False)
            system = forcefield.createSystem(newTopology)

            # Set any previously existing atoms to be massless, they so won't move.

            for atom in existingAtomMap.values():
                system.setParticleMass(atom.index, 0.0)

            # If any heavy atoms were omitted, add them back to avoid steric clashes.

            nonbonded = [f for f in system.getForces() if isinstance(f, mm.CustomNonbondedForce)][0]
            for atom in self.topology.atoms():
                if atom.element not in (None, hydrogen) and atom not in existingAtomMap:
                    system.addParticle(0.0)
                    nonbonded.addParticle([])
                    newPositions.append(self.positions[atom.index])

            # For efficiency, only compute interactions that involve a new atom.

            nonbonded.addInteractionGroup([atom.index for atom in newAtoms], range(system.getNumParticles()))

            # Do an energy minimization.

            integrator = mm.LangevinIntegrator(300*unit.kelvin, 10/unit.picosecond, 5*unit.femtosecond)
            if seed is not None:
                integrator.setRandomNumberSeed(seed)
            if self.platform is None:
                context = mm.Context(system, integrator)
            else:
                context = mm.Context(system, integrator, self.platform)
            context.setPositions(newPositions)
            mm.LocalEnergyMinimizer.minimize(context)
            state = context.getState(getPositions=True)
            if newTopology.getNumResidues() > 1:
                # When looking for pairs of atoms that are too close to each other, exclude pairs that
                # are in the same residue or are directly bonded to each other.

                exclusions = dict((atom, {a.index for a in atom.residue.atoms()}) for atom in newAtoms)
                for a1, a2 in newTopology.bonds():
                    if a1 in exclusions:
                        exclusions[a1].add(a2.index)
                    if a2 in exclusions:
                        exclusions[a2].add(a1.index)
                cutoff = 0.13
                nearest = self._findNearestDistance(context, newAtoms, cutoff, exclusions)
                if nearest < cutoff:

                    # Some atoms are very close together.  Run some dynamics while slowly increasing the strength of the
                    # repulsive interaction to try to improve the result.

                    for i in range(10):
                        context.setParameter('C', 0.15*(i+1))
                        integrator.step(200)
                        d = self._findNearestDistance(context, newAtoms, cutoff, exclusions)
                        if d > nearest:
                            nearest = d
                            state = context.getState(getPositions=True)
                            if nearest >= cutoff:
                                break
                    context.setState(state)
                    context.setParameter('C', 1.0)
                    mm.LocalEnergyMinimizer.minimize(context)
                    state = context.getState(getPositions=True)

            # Now create a new Topology, including all atoms from the original one and adding the missing atoms.

            (newTopology2, newPositions2, newAtoms2, existingAtomMap2) = self._addAtomsToTopology(False, False)

            # Copy over the minimized positions for the new atoms.

            for a1, a2 in zip(newAtoms, newAtoms2):
                newPositions2[a2.index] = state.getPositions()[a1.index]
            self.topology = newTopology2
            self.positions = newPositions2

    def removeHeterogens(self, keepWater=True,keepCoenzyme=False):
        """Remove all heterogens from the structure.

        Parameters
        ----------
        keepWater : bool, optional, default=True
            If True, water molecules will not be removed.

        Returns
        -------
        a list of Residue objects that were removed

        Examples
        --------

        Remove heterogens in Abl structure complexed with imatinib.

        >>> fixer = PDBFixer(pdbid='2F4J')
        >>> fixer.removeHeterogens(keepWater=False)

        """
        # If water and coenzymes are kept, do noting.
        if (keepWater and keepCoenzyme): 
            return ([])
        
        # Remove Coenzymes (ligands),keep waters
        if(not keepWater and not keepCoenzyme):
            keep = set(proteinResidues).union(dnaResidues).union(rnaResidues)
            keep.add('N')
            keep.add('UNK')
            toDelete = []
            for residue in self.topology.residues():
                if residue.name not in keep:
                    toDelete.append(residue)
            modeller = app.Modeller(self.topology, self.positions)
            modeller.delete(toDelete)
            self.topology = modeller.topology
            self.positions = modeller.positions
            return toDelete
        
        # Remove Coenzymes (ligands),keep waters
        if(keepWater and not keepCoenzyme):
            keep = set(proteinResidues).union(dnaResidues).union(rnaResidues)
            keep.add('N')
            keep.add('UNK')
            keep.add('HOH')
            toDelete = []
            for residue in self.topology.residues():
                if residue.name not in keep:
                    toDelete.append(residue)
            modeller = app.Modeller(self.topology, self.positions)
            modeller.delete(toDelete)
            self.topology = modeller.topology
            self.positions = modeller.positions
            return toDelete
        
        # Remove Waters and Coenzyme 
        if (not keepWater and keepCoenzyme):
            toDelete = []
            for residue in self.topology.residues():
                if residue.name == 'HOH':
                    toDelete.append(residue)
            modeller = app.Modeller(self.topology, self.positions)
            modeller.delete(toDelete)
            self.topology = modeller.topology
            self.positions = modeller.positions
            return toDelete

    def addMissingHydrogens2(self, pH=7.0, forcefield=None):
        """Add missing hydrogen atoms to the structure.

        Parameters
        ----------
        pH : float, optional, default=7.0
            The pH based on which to select hydrogens.
        forcefield : ForceField, optional, default=None
            The forcefield used when adding and minimizing hydrogens. If None, a default forcefield is used.

        Notes
        -----
        No extensive electrostatic analysis is performed; only default residue pKas are used.  The pH is only
        taken into account for standard amino acids.

        Examples
        --------

        Add missing hydrogens appropriate for pH 8.

        >>> fixer = PDBFixer(pdbid='1VII')
        >>> fixer.addMissingHydrogens(pH=8.0)
        """
        extraDefinitions = self._downloadNonstandardDefinitions()
        variants = [self._describeVariant(res, extraDefinitions) for res in self.topology.residues()]
        modeller = app.Modeller(self.topology, self.positions)
        modeller.addHydrogens(pH=pH, forcefield=forcefield, variants=variants, platform=self.platform)
        self.topology = modeller.topology
        self.positions = modeller.positions

    def addMissingHydrogens(self, pH=7.0, forcefield=None):
        """Add missing hydrogen atoms to the structure.

        Parameters
        ----------
        pH : float, optional, default=7.0
            The pH based on which to select hydrogens.
        forcefield : ForceField, optional, default=None
            The forcefield used when adding and minimizing hydrogens. If None, a default forcefield is used.

        Notes
        -----
        No extensive electrostatic analysis is performed; only default residue pKas are used.  The pH is only
        taken into account for standard amino acids.

        Examples
        --------

        Add missing hydrogens appropriate for pH 8.

        >>> fixer = PDBFixer(pdbid='1VII')
        >>> fixer.addMissingHydrogens(pH=8.0)
        """
        extraDefinitions = self._downloadNonstandardDefinitions()
        variants = []
        protein_atoms = []
        
        # First pass: identify protein atoms and residues
        for atom in self.topology.atoms():
            if atom.residue.name in proteinResidues:
                protein_atoms.append(atom.index)
        
        # Create a Modeller with only protein atoms
        modeller = app.Modeller(self.topology, self.positions)
        if len(protein_atoms) < self.topology.getNumAtoms():
            # Only keep protein atoms
            to_delete = [atom for atom in self.topology.atoms() if atom.index not in protein_atoms]
            modeller.delete(to_delete)
        
        # Now add hydrogens only to protein residues
        for res in modeller.topology.residues():
            variant = self._describeVariant(res, extraDefinitions)
            variants.append(variant)
        
        
        modeller.addHydrogens(pH=pH, forcefield=forcefield, variants=variants, platform=self.platform)
        

        # Merge back the original non-protein atoms with the new protein atoms that have hydrogens
        if len(protein_atoms) < self.topology.getNumAtoms():
        #if False:
            # Create a new topology combining original non-protein atoms with modified protein atoms
            new_topology = app.Topology()
            new_positions = []*unit.nanometer
            
            # Copy chains
            chain_map = {}
            for chain in self.topology.chains():
                new_chain = new_topology.addChain(chain.id)
                chain_map[chain] = new_chain
            
            # Copy residues and atoms
            atom_map = {}
            for residue in self.topology.residues():
                new_residue = new_topology.addResidue(residue.name, chain_map[residue.chain], residue.id, residue.insertionCode)
                
                if residue.name in proteinResidues:
                    # Find matching residue in modeller
                    mod_res = None
                    for mr in modeller.topology.residues():
                        if (mr.name == residue.name and 
                            mr.id == residue.id and 
                            mr.chain.id == residue.chain.id):
                            mod_res = mr
                            break
                    
                    if mod_res is None:
                        raise ValueError(f"Could not find matching residue {residue.name} {residue.id} in modeller")
                    
                    # Add all atoms from modeller residue (including new hydrogens)
                    for mod_atom in mod_res.atoms():
                        new_atom = new_topology.addAtom(mod_atom.name, mod_atom.element, new_residue)
                        atom_map[mod_atom] = new_atom
                        new_positions.append(modeller.positions[mod_atom.index])
                
                # Handle non-protein residues (original atoms)
                else:
                    for atom in residue.atoms():
                        new_atom = new_topology.addAtom(atom.name, atom.element, new_residue)
                        atom_map[atom] = new_atom
                        new_positions.append(self.positions[atom.index])
            
            # Copy bonds
            #for bond in self.topology.bonds():
            #    if bond[0] in atom_map and bond[1] in atom_map:
            #        new_topology.addBond(atom_map[bond[0]], atom_map[bond[1]])
            
            self.topology = new_topology
            self.positions = new_positions
        else:
            self.topology = modeller.topology
            self.positions = modeller.positions

    def _downloadNonstandardDefinitions(self):
        """If the file contains any nonstandard residues, download their definitions and build
        the information needed to add hydrogens to them.
        """
        app.Modeller._loadStandardHydrogenDefinitions()
        resnames = set(residue.name for residue in self.topology.residues())
        definitions = {}
        for name in resnames:
            if name not in app.Modeller._residueHydrogens:
                # Try to download the definition.
                ccdDefinition = self._downloadCCDDefinition(name)
                if ccdDefinition is None:
                    continue

                # Record the atoms and bonds.
                atoms = [(atom.atomName, atom.symbol.upper(), atom.leaving) for atom in ccdDefinition.atoms]
                bonds = [(bond.atom1, bond.atom2) for bond in ccdDefinition.bonds]
                definitions[name] = (atoms, bonds)
        return definitions

    def _describeVariant(self, residue, definitions):
        """Build the variant description to pass to addHydrogens() for a residue."""
        if residue.name not in self._standardTemplates and self._getTemplate(residue.name) is not None:
            # The user has registered a template for this residue.  Use the hydrogens from it.
            template = self._getTemplate(residue.name)
            atoms = [(atom.name, atom.element.symbol.upper(), terminal) for atom, terminal in zip(template.topology.atoms(), template.terminal)]
            resAtoms = dict((atom.name, atom) for atom in residue.atoms())
            bonds = []
            for atom1, atom2 in template.topology.bonds():
                if atom1.element == app.element.hydrogen and atom2.name in resAtoms:
                    bonds.append((atom1.name, atom2.name))
                elif atom2.element == app.element.hydrogen and atom1.name in resAtoms:
                    bonds.append((atom2.name, atom1.name))
        elif residue.name in definitions:
            # We downloaded a definition.
            atoms, bonds = definitions[residue.name]
        else:
            return None

        # See if the heavy atoms are identical.

        topologyHeavy = dict((atom.name, atom) for atom in residue.atoms() if atom.element is not None and atom.element != app.element.hydrogen)
        definitionHeavy = dict((atom[0], atom) for atom in atoms if atom[1] != '' and atom[1] != 'H')
        for name in topologyHeavy:
            if name not in definitionHeavy or definitionHeavy[name][1] != topologyHeavy[name].element.symbol.upper():
                # This atom isn't present in the definition
                return None
        for name in definitionHeavy:
            if name not in topologyHeavy and not definitionHeavy[name][2]:
                # This isn't a leaving atom, and it isn't present in the topology.
                return None

        # Build the list of hydrogens.

        variant = []
        definitionAtoms = dict((atom[0], atom) for atom in atoms)
        topologyBonds = list(residue.bonds())
        for name1, name2 in bonds:
            if definitionAtoms[name1][1] == 'H':
                h, parent = name1, name2
            elif definitionAtoms[name2][1] == 'H':
                h, parent = name2, name1
            else:
                continue
            if definitionAtoms[h][2]:
                # The hydrogen is marked as a leaving atom.  Omit it if the parent is not present,
                # or if the parent has an external bond.
                if parent not in topologyHeavy:
                    continue
                parentAtom = topologyHeavy[parent]
                exclude = False
                for atom1, atom2 in topologyBonds:
                    if atom1 == parentAtom and atom2.residue != residue:
                        exclude = True
                        break
                    if atom2 == parentAtom and atom1.residue != residue:
                        exclude = True
                        break
                if exclude:
                    continue
            variant.append((h, parent))
        return variant

    def addSolvent(self, boxSize=None, padding=None, boxVectors=None, positiveIon='Na+', negativeIon='Cl-', ionicStrength=0*unit.molar, boxShape='cube', forceField=None):
        """Add a solvent box surrounding the structure.

        Parameters
        ----------
        boxSize : openmm.Vec3, optional, default=None
            The size of the box to fill with water.  If specified, padding and boxVectors must not be specified.
        padding : openmm.unit.Quantity compatible with nanometers, optional, default=None
            Padding around macromolecule for filling box with water.  If specified, boxSize and boxVectors must not be specified.
        boxVectors : 3-tuple of openmm.Vec3, optional, default=None
            Three vectors specifying the geometry of the box. If specified, padding and boxSize must not be specified.
        positiveIon : str, optional, default='Na+'
            The type of positive ion to add.  Allowed values are 'Cs+', 'K+', 'Li+', 'Na+', and 'Rb+'.
        negativeIon : str, optional, default='Cl-'
            The type of negative ion to add.  Allowed values are 'Cl-', 'Br-', 'F-', and 'I-'.
        ionicStrength : openmm.unit.Quantity with units compatible with molar, optional, default=0*molar
            The total concentration of ions (both positive and negative) to add.  This does not include ions that are added to neutralize the system.
        boxShape : str='cube'
            The box shape to use.  Allowed values are 'cube', 'dodecahedron', and 'octahedron'.  If padding is None, this is ignored.
        forceField : openmm.app.ForceField, optional
            The force field to use for determining van der Waals radii and
            atomic charges. If not set, a force field will be generated. If the
            solvated topology has a nonzero total charge, provide a force field
            that correctly charges the solute.

        Examples
        --------

        Add missing residues, heavy atoms, and hydrogens, and then solvate with 10 A padding.

        >>> fixer = PDBFixer(pdbid='1VII')
        >>> fixer.findMissingResidues()
        >>> fixer.findMissingAtoms()
        >>> fixer.addMissingAtoms()
        >>> fixer.addMissingHydrogens(pH=8.0)
        >>> fixer.addSolvent(padding=10*unit.angstrom, ionicStrength=0.050*unit.molar)

        """

        nChains = sum(1 for _ in self.topology.chains())
        modeller = app.Modeller(self.topology, self.positions)
        if forceField is None:
            forceField = self._createForceField(self.topology, True)
        modeller.addSolvent(forceField, padding=padding, boxSize=boxSize, boxVectors=boxVectors, boxShape=boxShape, positiveIon=positiveIon, negativeIon=negativeIon, ionicStrength=ionicStrength)
        self.topology = modeller.topology
        self.positions = modeller.positions
        self._renameNewChains(nChains)

    def addMembrane(self, lipidType='POPC', membraneCenterZ=0*unit.nanometer, minimumPadding=1*unit.nanometer, positiveIon='Na+', negativeIon='Cl-', ionicStrength=0*unit.molar):
        """Add a lipid membrane to the structure.

        This method adds both lipids and water, so you should call either addSolvent() or addMembrane(),
        but not both.  See Modeller.addMembrane() for more details.

        Parameters
        ----------
        lipidType : string='POPC'
            the type of lipid to use.  Supported values are 'POPC', 'POPE', 'DLPC', 'DLPE', 'DMPC', 'DOPC', and 'DPPC'.
        membraneCenterZ: distance=0*nanometer
            the position along the Z axis of the center of the membrane
        minimumPadding : distance=1*nanometer
            the padding distance to use
        positiveIon : str, optional, default='Na+'
            The type of positive ion to add.  Allowed values are 'Cs+', 'K+', 'Li+', 'Na+', and 'Rb+'.
        negativeIon : str, optional, default='Cl-'
            The type of negative ion to add.  Allowed values are 'Cl-', 'Br-', 'F-', and 'I-'.
        ionicStrength : openmm.unit.Quantity with units compatible with molar, optional, default=0*molar
            The total concentration of ions (both positive and negative) to add.  This does not include ions that are added to neutralize the system.
        """

        nChains = sum(1 for _ in self.topology.chains())
        modeller = app.Modeller(self.topology, self.positions)
        forcefield = self._createForceField(self.topology, True)
        modeller.addMembrane(forcefield, lipidType=lipidType, membraneCenterZ=membraneCenterZ, minimumPadding=minimumPadding, positiveIon=positiveIon, negativeIon=negativeIon, ionicStrength=ionicStrength)
        self.topology = modeller.topology
        self.positions = modeller.positions
        self._renameNewChains(nChains)

    def _downloadFormalCharges(self, resName: str, includeLeavingAtoms: bool = True) -> dict[str, int]:
        """
        Download the formal charges for a residue name from the CCD

        Returns
        -------
        formalCharges
            Dictionary mapping from atom names (``str``) to formal charges (``int``)
        """
        # Try to download the definition.
        ccdDefinition = self._downloadCCDDefinition(resName.upper())
        if ccdDefinition is None:
            return {}

        # Record the formal charges.
        return {
            atom.atomName: atom.charge
            for atom in ccdDefinition.atoms
            if includeLeavingAtoms or not atom.leaving
        }

    def _createForceField(self, newTopology, water):
        """Create a force field to use for optimizing the positions of newly added atoms."""

        if water:
            forcefield = app.ForceField('amber14-all.xml', 'amber14/tip3p.xml')
            nonbonded = [f for f in forcefield._forces if isinstance(f, NonbondedGenerator)][0]
            radii = {'H':0.198, 'Li':0.203, 'C':0.340, 'N':0.325, 'O':0.299, 'F':0.312, 'Na':0.333, 'Mg':0.141,
                     'P':0.374, 'S':0.356, 'Cl':0.347, 'K':0.474, 'Br':0.396, 'Rb':0.527, 'I':0.419, 'Cs':0.605}
        else:
            forcefield = app.ForceField(os.path.join(os.path.dirname(__file__), 'soft.xml'))

        # The Topology may contain residues for which the ForceField does not have a template.
        # If so, we need to create new templates for them.

        atomTypes = {}
        bondedToAtom = []
        for atom in newTopology.atoms():
            bondedToAtom.append(set())
        for atom1, atom2 in newTopology.bonds():
            bondedToAtom[atom1.index].add(atom2.index)
            bondedToAtom[atom2.index].add(atom1.index)
        for residue in newTopology.residues():

            # Make sure the ForceField has a template for this residue.

            signature = app.forcefield._createResidueSignature([atom.element for atom in residue.atoms()])
            if signature in forcefield._templateSignatures:
                if any(matchResidue(residue, t, bondedToAtom) is not None for t in forcefield._templateSignatures[signature]):
                    continue

            # Create a new template.

            resName = "extra_"+residue.name
            template = app.ForceField._TemplateData(resName)
            forcefield._templates[resName] = template
            indexInResidue = {}
            # If we can't find formal charges in the CCD, make everything uncharged
            formalCharges = defaultdict(int)
            # See if we can get formal charges from the CCD
            if water:
                # The formal charges in the CCD can only be relied on if the
                # residue has all and only the same atoms, with the caveat that
                # leaving atoms are optional
                downloadedFormalCharges = self._downloadFormalCharges(residue.name)
                essentialAtoms = set(
                    self._downloadFormalCharges(residue.name, includeLeavingAtoms=False)
                )
                atomsInResidue = {atom.name for atom in residue.atoms()}
                if (
                    atomsInResidue.issuperset(essentialAtoms)
                    and atomsInResidue.issubset(downloadedFormalCharges)
                ):
                    # We got formal charges and the atom names match, so we can use them
                    formalCharges = downloadedFormalCharges
            for atom in residue.atoms():
                element = atom.element
                formalCharge = formalCharges.get(atom.name, 0)
                typeName = 'extra_'+element.symbol+'_'+str(formalCharge)
                if (element, formalCharge) not in atomTypes:
                    atomTypes[(element, formalCharge)] = app.ForceField._AtomType(typeName, '', 0.0, element)
                    forcefield._atomTypes[typeName] = atomTypes[(element, formalCharge)]
                    if water:
                        # Select a reasonable vdW radius for this atom type.

                        if element.symbol in radii:
                            sigma = radii[element.symbol]
                        else:
                            sigma = 0.5
                        nonbonded.registerAtom({
                            'type':typeName,
                            'charge':str(formalCharge),
                            'sigma':str(sigma),
                            'epsilon':'0'
                        })
                indexInResidue[atom.index] = len(template.atoms)
                template.atoms.append(app.ForceField._TemplateAtomData(atom.name, typeName, element))
            for atom in residue.atoms():
                for bondedTo in bondedToAtom[atom.index]:
                    if bondedTo in indexInResidue:
                        b = (indexInResidue[atom.index], indexInResidue[bondedTo])
                        if b[0] < b[1]:
                            template.bonds.append(b)
                            template.atoms[b[0]].bondedTo.append(b[1])
                            template.atoms[b[1]].bondedTo.append(b[0])
                    else:
                        b = indexInResidue[atom.index]
                        template.externalBonds.append(b)
                        template.atoms[b].externalBonds += 1
            if signature in forcefield._templateSignatures:
                forcefield._templateSignatures[signature].append(template)
            else:
                forcefield._templateSignatures[signature] = [template]
        return forcefield

    def _findNearestDistance(self, context, newAtoms, cutoff, exclusions):
        """Given a set of newly added atoms, find the closest distance between one of those atoms and another atom."""

        positions = context.getState(getPositions=True).getPositions(asNumpy=True).value_in_unit(unit.nanometer)
        boxSize = np.max(positions, axis=0)-np.min(positions, axis=0)
        boxVectors = [(boxSize[0], 0, 0), (0, boxSize[1], 0), (0, 0, boxSize[2])]
        cells = app.modeller._CellList(positions, cutoff, boxVectors, False)
        nearest_squared = sys.float_info.max
        for atom in newAtoms:
            excluded = exclusions[atom]
            for i in cells.neighbors(positions[atom.index]):
                if i not in excluded:
                    p = positions[atom.index]-positions[i]
                    dist_squared = np.dot(p, p)
                    if dist_squared < nearest_squared:
                        nearest_squared = dist_squared
        return np.sqrt(nearest_squared)



    def atomicOPT(self, residueList=None):
        """optmized geometry.

        Parameters
        ----------
        resdueList : list, optional, default=None
            If None, optmized all atoms (heavy and H atoms)
            If a list provided, only the heavy atoms in the list and H atoms are optimized 

        Notes
        -----
            The added residues are not well optmized. 

        """
        from openmm.app import ForceField
        from openmm.app.forcefield import NoCutoff,HBonds
        from openmm.app.simulation import Simulation
        from openmm import LangevinMiddleIntegrator
        from openmm.app.pdbfile import PDBFile
        from sys import stdout

        extraDefinitions = self._downloadNonstandardDefinitions()
        variants = []
        protein_atoms = []
        
        # First pass: identify protein atoms and residues
        for atom in self.topology.atoms():
            if atom.residue.name in proteinResidues:
                protein_atoms.append(atom.index)
        
        # Create a Modeller with only protein atoms
        modeller = app.Modeller(self.topology, self.positions)
        if len(protein_atoms) < self.topology.getNumAtoms():
            # Only keep protein atoms
            to_delete = [atom for atom in self.topology.atoms() if atom.index not in protein_atoms]
            modeller.delete(to_delete)
        
        # Now add hydrogens only to protein residues
        for res in modeller.topology.residues():
            variant = self._describeVariant(res, extraDefinitions)
            variants.append(variant)

        PDBFile.writeFile(modeller.topology, modeller.positions, open('temp.pdb', 'w'))
        # Do optimization 
        pdb = PDBFile('temp.pdb')
        forcefield = ForceField('amber14-all.xml', 'amber14/tip3pfb.xml')
        #system = forcefield.createSystem(modeller.topology, nonbondedMethod=NoCutoff, nonbondedCutoff=1*unit.nanometer, constraints=HBonds)
        system = forcefield.createSystem(pdb.topology, nonbondedMethod=NoCutoff, nonbondedCutoff=1*unit.nanometer, constraints=HBonds)
        integrator = LangevinMiddleIntegrator(300*unit.kelvin, 1/unit.picosecond, 0.004*unit.picoseconds)
        #simulation = Simulation(modeller.topology, system, integrator)
        simulation = Simulation(pdb.topology, system, integrator)
        simulation.context.setPositions(pdb.positions)
        #simulation.context.setPositions(modeller.positions)
        simulation.minimizeEnergy(tolerance=100 * unit.kilojoule/unit.mole/unit.nanometer)
        state = simulation.context.getState(getPositions=True, getEnergy=True)


        #modeller.addHydrogens(pH=pH, forcefield=forcefield, variants=variants, platform=self.platform)
        modeller.topology = simulation.topology
        modeller.positions = state.getPositions()
        # Merge back the original non-protein atoms with the new protein atoms that have hydrogens
        if len(protein_atoms) < self.topology.getNumAtoms():
        #if False:
            # Create a new topology combining original non-protein atoms with modified protein atoms
            new_topology = app.Topology()
            new_positions = []*unit.nanometer
            
            # Copy chains
            chain_map = {}
            for chain in self.topology.chains():
                new_chain = new_topology.addChain(chain.id)
                chain_map[chain] = new_chain
        

            # Copy residues and atoms
            atom_map = {}
            proteir_resID_ori = 0
            for residue in self.topology.residues():
                new_residue = new_topology.addResidue(residue.name, chain_map[residue.chain], residue.id, residue.insertionCode)
                proteir_resID_ori = proteir_resID_ori + 1
                
                if residue.name in proteinResidues:
                    # Find matching residue in modeller
                    mod_res = None
                    proteir_resID_new = 0
                    for mr in modeller.topology.residues():
                        print(mr.name,residue.name, mr.id, residue.id, mr.chain.id, residue.chain.id,proteir_resID_new,proteir_resID_ori)
                        proteir_resID_new = proteir_resID_new+1
                        if (mr.name == residue.name and 
                            proteir_resID_new == proteir_resID_ori  and # Some are not start from zero 
                            mr.chain.id == residue.chain.id):
                            mod_res = mr
                            break
                    
                    if mod_res is None:
                        raise ValueError(f"Could not find matching residue {residue.name} {residue.id} in modeller")
                    
                    # Add all atoms from modeller residue (including new hydrogens)
                    for mod_atom in mod_res.atoms():
                        new_atom = new_topology.addAtom(mod_atom.name, mod_atom.element, new_residue)
                        atom_map[mod_atom] = new_atom
                        new_positions.append(modeller.positions[mod_atom.index])

                
                # Handle non-protein residues (original atoms)
                else:
                    for atom in residue.atoms():
                        new_atom = new_topology.addAtom(atom.name, atom.element, new_residue)
                        atom_map[atom] = new_atom
                        new_positions.append(self.positions[atom.index])
            
            # Copy bonds
            #for bond in self.topology.bonds():
            #    if bond[0] in atom_map and bond[1] in atom_map:
            #        new_topology.addBond(atom_map[bond[0]], atom_map[bond[1]])
            
            self.topology = new_topology
            self.positions = new_positions
        else:
            self.topology = modeller.topology
            self.positions = modeller.positions



def main():
    if len(sys.argv) < 2:
        # Display the UI.
        from . import ui
        ui.launchUI()
    else:
        # Run in command line mode.

        from optparse import OptionParser
        parser = OptionParser(usage="Usage: %prog\n       %prog filename [options] \n\nWhen run with no arguments, it launches the user interface.  If any arguments are specified, it runs in command line mode.")
        parser.add_option('--pdbid', default=None, dest='pdbid', metavar='PDBID', help='PDB id to retrieve from RCSB [default: None]')
        parser.add_option('--url', default=None, dest='url', metavar='URL', help='URL to retrieve PDB from [default: None]')
        parser.add_option('--output', default='output.pdb', dest='output', metavar='FILENAME', help='output pdb file [default: output.pdb]')
        parser.add_option('--add-atoms', default='all', dest='atoms', choices=('all', 'heavy', 'hydrogen', 'none'), help='which missing atoms to add: all, heavy, hydrogen, or none [default: all]')
        parser.add_option('--keep-heterogens', default='all', dest='heterogens', choices=('all', 'water', 'none'), metavar='OPTION', help='which heterogens to keep: all, water, or none [default: all]')
        parser.add_option('--replace-nonstandard', action='store_true', default=False, dest='nonstandard', help='replace nonstandard residues with standard equivalents')
        parser.add_option('--add-residues', action='store_true', default=False, dest='residues', help='add missing residues')
        parser.add_option('--water-box', dest='box', type='float', nargs=3, metavar='X Y Z', help='add a water box. The value is the box dimensions in nm [example: --water-box=2.5 2.4 3.0]')
        parser.add_option('--ph', type='float', default=7.0, dest='ph', help='the pH to use for adding missing hydrogens [default: 7.0]')
        parser.add_option('--positive-ion', default='Na+', dest='positiveIon', choices=('Cs+', 'K+', 'Li+', 'Na+', 'Rb+'), metavar='ION', help='positive ion to include in the water box: Cs+, K+, Li+, Na+, or Rb+ [default: Na+]')
        parser.add_option('--negative-ion', default='Cl-', dest='negativeIon', choices=('Cl-', 'Br-', 'F-', 'I-'), metavar='ION', help='negative ion to include in the water box: Cl-, Br-, F-, or I- [default: Cl-]')
        parser.add_option('--ionic-strength', type='float', default=0.0, dest='ionic', metavar='STRENGTH', help='molar concentration of ions to add to the water box [default: 0.0]')
        parser.add_option('--verbose', default=False, action='store_true', dest='verbose', metavar='VERBOSE', help='Print verbose output')
        (options, args) = parser.parse_args()
        if (len(args) == 0) and (options.pdbid==None) and (options.url==None):
            parser.error('No filename specified')
        if len(args) > 1:
            parser.error('Must specify a single filename or --pdbid or --url')
        if options.pdbid != None:
            if options.verbose: print('Retrieving PDB "' + options.pdbid + '" from RCSB...')
            fixer = PDBFixer(pdbid=options.pdbid)
        elif options.url != None:
            if options.verbose: print('Retrieving PDB from URL "' + options.url + '"...')
            fixer = PDBFixer(url=options.url)
        else:
            fixer = PDBFixer(filename=sys.argv[1])
        if options.residues:
            if options.verbose: print('Finding missing residues...')
            fixer.findMissingResidues()
        else:
            fixer.missingResidues = {}
        if options.nonstandard:
            if options.verbose: print('Finding nonstandard residues...')
            fixer.findNonstandardResidues()
            if options.verbose: print('Replacing nonstandard residues...')
            fixer.replaceNonstandardResidues()
        if options.heterogens == 'none':
            fixer.removeHeterogens(False)
        elif options.heterogens == 'water':
            fixer.removeHeterogens(True)
        if options.verbose: print('Finding missing atoms...')
        fixer.findMissingAtoms()
        if options.atoms not in ('all', 'heavy'):
            fixer.missingAtoms = {}
            fixer.missingTerminals = {}
        if options.verbose: print('Adding missing atoms...')
        fixer.addMissingAtoms()
        if options.atoms in ('all', 'hydrogen'):
            if options.verbose: print('Adding missing hydrogens...')
            fixer.addMissingHydrogens(options.ph)
        if options.box is not None:
            if options.verbose: print('Adding solvent...')
            fixer.addSolvent(boxSize=options.box*unit.nanometer, positiveIon=options.positiveIon,
                negativeIon=options.negativeIon, ionicStrength=options.ionic*unit.molar)
        with open(options.output, 'w') as f:
            if options.verbose: print('Writing output...')
            if fixer.source is not None:
                f.write("REMARK   1 PDBFIXER FROM: %s\n" % fixer.source)
            app.PDBFile.writeFile(fixer.topology, fixer.positions, f, True)
        if options.verbose: print('Done.')

if __name__ == '__main__':
    main()
