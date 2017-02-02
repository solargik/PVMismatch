# -*- coding: utf-8 -*-
"""
This module defines the :class:`~pvmismatch.pvmismatch_lib.pvmodule.PVmodule`.
"""

import numpy as np
from copy import copy
from matplotlib import pyplot as plt
# use absolute imports instead of relative, so modules are portable
from pvmismatch.pvmismatch_lib.pvconstants import PVconstants, get_series_cells
from pvmismatch.pvmismatch_lib.pvcell import PVcell

VBYPASS = np.float64(-0.5)  # [V] trigger voltage of bypass diode
CELLAREA = np.float64(153.33)  # [cm^2] cell area


def standard_cellpos_pat(nrows, ncols_per_substr):
    """
    Standard module object builder.

    Parameters
    ----------
    nrows : integer
        Number of rows of cells in module.

    ncols_per_substr : list of integers
        Number of columns of cells in each substring (in parallel with a diode).

    Returns
    -------
    cellpos : list of lists
         Outermost list is a list of substrings in parallel with a bypass diode
         and in series with each other.
         The substring is a list of columns in that substring.
         Inside the column are the actual cells in each row.
         Each cell has a 'crosstie' key and an index.
    """
    cellpos = []
    ncols = [0, 0]
    for substr_cols in ncols_per_substr:
        ncols[0], ncols[1] = ncols[1], ncols[1] + substr_cols
        newsubstr = []
        for col in xrange(*ncols):
            newrow = []
            for row in xrange(nrows):
                idx = col * nrows
                if col % 2 == 0:
                    idx += row
                else:
                    idx += (nrows - row - 1)
                newrow.append({'crosstie': False, 'idx': idx})
            newsubstr.append(newrow)
        cellpos.append(newsubstr)
    return cellpos

# standard cell positions presets
STD24 = standard_cellpos_pat(1, [1] * 24)
STD72 = standard_cellpos_pat(12, [2, 2, 2])
STD96 = standard_cellpos_pat(12, [2, 4, 2])
"""
Standard module: 12x8 cells
Substrings have 2, 4 and 2 columns of cells per diode
"""
STD128 = standard_cellpos_pat(16, [2, 4, 2])


def crosstied_cellpos_pat(nrows_per_substrs, ncols, partial=False):
    """
    Cross-tied module object builder.

    Parameters
    ----------
    nrows_per_substr : list of integers
        Number of rows of cells in each substring (in parallel with a diode).

    ncols : integer
        Number of columns of cells.
        
    partial : boolean
        False (default) means TCT (all cells are cross-tied).
        True means no cross-tiling.

    Returns
    -------
    cellpos : list of lists
         Outermost list is a list of substrings in parallel with a bypass diode
         and in series with each other.
         The substring is a list of columns in that substring.
         Inside the column are the actual cells in each row.
         Each cell has a 'crosstie' key and an index.
    """
    trows = sum(nrows_per_substrs)
    cellpos = []
    nrows = [0, 0]
    for substr_row in nrows_per_substrs:
        nrows[0], nrows[1] = nrows[1], nrows[1] + substr_row
        newsubstr = []
        for col in xrange(ncols):
            newrow = []
            for row in xrange(*nrows):
                crosstie = True
                if partial and newrow:
                    crosstie = False
                newrow.append({'crosstie': crosstie, 'idx': col * trows + row})
            newsubstr.append(newrow)
        cellpos.append(newsubstr)
    return cellpos

# crosstied cell positions presets
TCT492 = crosstied_cellpos_pat([27, 28, 27], 6)
"""
Standard Tiled module with total cross-ties: 82x6 cells
Substrings have 27, 28 and 27 rows of cells per diode
"""
PCT492 = crosstied_cellpos_pat([27, 28, 27], 6, partial=True)
"""
Standard Tiled module with partial cross-ties: 82x6 cells
Substrings have 27, 28 and 27 rows of cells per diode
"""

def combine_parallel_circuits(IVprev_cols, pvconst):
    """
    Combine crosstied circuits in a substring

    :param IVprev_cols: lists of IV curves of crosstied and series circuits
    :return:
    """
    # combine crosstied circuits
    Irows, Vrows = [], []
    Isc_rows, Imax_rows = [], []
    for IVcols in zip(*IVprev_cols):
        Iparallel, Vparallel = zip(*IVcols)
        Iparallel = np.asarray(Iparallel)
        Vparallel = np.asarray(Vparallel)
        Irow, Vrow = pvconst.calcParallel(
            Iparallel, Vparallel, Vparallel.max(),
            Vparallel.min()
        )
        Irows.append(Irow)
        Vrows.append(Vrow)
        Isc_rows.append(np.interp(np.float64(0), Vrow, Irow))
        Imax_rows.append(Irow.max())
    Irows, Vrows = np.asarray(Irows), np.asarray(Vrows)
    Isc_rows = np.asarray(Isc_rows)
    Imax_rows = np.asarray(Imax_rows)
    return pvconst.calcSeries(
        Irows, Vrows, Isc_rows.mean(), Imax_rows.max()
    )

class PVmodule(object):
    """
    A Class for PV modules.

    :param cell_pos: cell position pattern
    :type cell_pos: dict
    :param pvcells: list of :class:`~pvmismatch.pvmismatch_lib.pvcell.PVcell`
    :type pvcells: list
    :param pvconst: An object with common parameters and constants.
    :type pvconst: :class:`~pvmismatch.pvmismatch_lib.pvconstants.PVconstants`
    :param Vbypass: bypass diode trigger voltage [V]
    :param cellArea: cell area [cm^2]
    """
    def __init__(self, cell_pos=STD96, pvcells=None, pvconst=PVconstants(),
                 Vbypass=VBYPASS, cellArea=CELLAREA):
        # TODO: check cell position pattern
        self.cell_pos = cell_pos  #: cell position pattern dictionary
        self.numberCells = sum([len(c) for s in self.cell_pos for c in s])
        """number of cells in the module"""
        self.pvconst = pvconst  #: configuration constants
        self.Vbypass = Vbypass  #: [V] trigger voltage of bypass diode
        self.cellArea = cellArea  #: [cm^2] cell area
        if pvcells is None:
            # faster to use copy instead of making each object in a for-loop
            # use copy instead of deepcopy to keep same pvconst for all objects
            # PVcell.calcCell() creates new np.ndarray if attributes change
            pvcells = PVcell(pvconst=self.pvconst)
        if isinstance(pvcells, PVcell):
            pvcells = [pvcells] * self.numberCells
        if len(pvcells) != self.numberCells:
            # TODO: use pvexception
            raise Exception(
                "Number of cells doesn't match cell position pattern."
            )
        self.pvcells = pvcells  #: list of `PVcell` objects in this `PVmodule`
        self.numSubStr = len(self.cell_pos)  #: number of substrings
        self.subStrCells = [len(_) for _ in self.cell_pos]  #: cells per substr
        # initialize members so PyLint doesn't get upset
        self.Imod, self.Vmod, self.Pmod, self.Isubstr, self.Vsubstr = self.calcMod()

    # TODO: use __getattr__ to check for updates to pvcells

    # copy some values from cells to modules
    @property
    def Ee(self):
        return np.array([pvc.Ee.flatten() for pvc in self.pvcells])

    @property
    def Tcell(self):
        return np.array([pvc.Tcell.flatten() for pvc in self.pvcells])

    @property
    def Icell(self):
        return np.array([pvc.Icell.flatten() for pvc in self.pvcells])

    @property
    def Vcell(self):
        return np.array([pvc.Vcell.flatten() for pvc in self.pvcells])

    @property
    def Pcell(self):
        return np.array([pvc.Pcell.flatten() for pvc in self.pvcells])

    @property
    def Isc(self):
        return np.array([pvc.Isc.flatten() for pvc in self.pvcells])

    @property
    def Voc(self):
        return np.array([pvc.Voc.flatten() for pvc in self.pvcells])

    @property
    def VRBD(self):
        return np.array([pvc.VRBD.flatten() for pvc in self.pvcells])

    def setSuns(self, Ee, cells=None):
        """
        Set the irradiance in suns, Ee, on the solar cells in the module.
        Recalculates cell current (Icell [A]), voltage (Vcell [V]) and power
        (Pcell [W]) as well as module current (Imod [A]), voltage (Vmod [V])
        and power (Pmod [W]).

        Args:
            Ee (:class:`numpy.ndarray`): Effective Irradiance [suns]
            cells (list): Cells to change [Optional]
        """
        if cells is None:
            if np.isscalar(Ee):
                new_pvcells = range(self.numberCells)  # new list of cells
                old_pvcells = dict.fromkeys(self.pvcells)  # same as set(pvcells)
                for cell_id, pvcell in enumerate(self.pvcells):
                    if old_pvcells[pvcell] is None:
                        new_pvcells[cell_id] = copy(pvcell)
                        old_pvcells[pvcell] = new_pvcells[cell_id]
                    else:
                        new_pvcells[cell_id] = old_pvcells[pvcell]
                self.pvcells = new_pvcells
                pvcell_set = old_pvcells.itervalues()
                for pvc in pvcell_set:
                    pvc.Ee = Ee
            elif np.size(Ee) == self.numberCells:
                self.pvcells = copy(self.pvcells)  # copy list first
                for cell_idx, Ee_idx in enumerate(Ee):
                    self.pvcells[cell_idx] = copy(self.pvcells[cell_idx])
                    self.pvcells[cell_idx].Ee = Ee_idx
            else:
                raise Exception("Input irradiance value (Ee) for each cell!")
        else:
            Ncells = np.size(cells)
            self.pvcells = copy(self.pvcells)  # copy list first
            if np.isscalar(Ee):
                cells_to_update = [self.pvcells[i] for i in cells]
                old_pvcells = dict.fromkeys(cells_to_update)
                for cell_id, pvcell in zip(cells, cells_to_update):
                    if old_pvcells[pvcell] is None:
                        self.pvcells[cell_id] = copy(pvcell)
                        self.pvcells[cell_id].Ee = Ee
                        old_pvcells[pvcell] = self.pvcells[cell_id]
                    else:
                        self.pvcells[cell_id] = old_pvcells[pvcell]
            elif np.size(Ee) == Ncells:
                # Find unique irradiance values
                # TODO possible "cleaner" alternative by grouping cells into tuples that match the set irradiance
                # E.g: pvsys.setSuns({X: {Y: {'Ee': (0.33, 0.99), 'cells': [(2, 3), 17]}}})
                cells = np.array(cells)
                Ee = np.array(Ee)
                unique_ee = np.unique(Ee)
                for a_Ee in unique_ee:
                    cells_subset = cells[np.where(Ee == a_Ee)]
                    cells_to_update = [self.pvcells[i] for i in cells_subset]
                    old_pvcells = dict.fromkeys(cells_to_update)
                    for cell_id, pvcell in zip(cells_subset, cells_to_update):
                        if old_pvcells[pvcell] is None:
                            self.pvcells[cell_id] = copy(pvcell)
                            self.pvcells[cell_id].Ee = a_Ee
                            old_pvcells[pvcell] = self.pvcells[cell_id]
                        else:
                            self.pvcells[cell_id] = old_pvcells[pvcell]
            else:
                raise Exception("Input irradiance value (Ee) for each cell!")
        self.Imod, self.Vmod, self.Pmod, self.Isubstr, self.Vsubstr = self.calcMod()

    def calcMod(self):
        """
        Calculate module I-V curves.

        Returns module currents [A], voltages [V] and powers [W]
        """
        # iterate over substrings
        # TODO: benchmark speed difference append() vs preallocate space
        Isubstr, Vsubstr, Isc_substr, Imax_substr = [], [], [], []
        for substr in self.cell_pos:
            # check if cells are in series or any crosstied circuits
            if all(r['crosstie'] == False for c in substr for r in c):
                idxs = [r['idx'] for c in substr for r in c]
                IatVrbd = np.asarray(
                    [np.interp(vrbd, v, i) for vrbd, v, i in
                     zip(self.VRBD[idxs], self.Vcell[idxs], self.Icell[idxs])]
                )
                Isub, Vsub = self.pvconst.calcSeries(
                    self.Icell[idxs], self.Vcell[idxs], self.Isc[idxs].mean(),
                    IatVrbd.max()
                )
            elif all(r['crosstie'] == True for c in substr for r in c):
                Irows, Vrows = [], []
                Isc_rows, Imax_rows = [], []
                for row in zip(*substr):
                    idxs = [c['idx'] for c in row]
                    Irow, Vrow = self.pvconst.calcParallel(
                        self.Icell[idxs], self.Vcell[idxs],
                        self.Voc[idxs].max(), self.VRBD.min()
                    )
                    Irows.append(Irow)
                    Vrows.append(Vrow)
                    Isc_rows.append(np.interp(np.float64(0), Vrow, Irow))
                    Imax_rows.append(Irow.max())
                Irows, Vrows = np.asarray(Irows), np.asarray(Vrows)
                Isc_rows = np.asarray(Isc_rows)
                Imax_rows = np.asarray(Imax_rows)
                Isub, Vsub = self.pvconst.calcSeries(
                    Irows, Vrows, Isc_rows.mean(), Imax_rows.max()
                )
            else:
                IVall_cols = []
                prev_col = None
                IVprev_cols = []
                for col in substr:
                    IVcols = []
                    is_first = True
                    # combine series between crossties
                    for idxs in get_series_cells(col, prev_col):
                        if not idxs:
                            # first row should always be empty since it must be
                            # crosstied
                            is_first = False
                            continue
                        elif is_first:
                            # TODO: use pvmismatch exceptions
                            raise Exception(
                                "First row and last rows must be crosstied."
                            )
                        elif len(idxs) > 1:
                            IatVrbd = np.asarray(
                                [np.interp(vrbd, v, i) for vrbd, v, i in
                                 zip(self.VRBD[idxs], self.Vcell[idxs],
                                     self.Icell[idxs])]
                            )
                            Icol, Vcol = self.pvconst.calcSeries(
                                self.Icell[idxs], self.Vcell[idxs],
                                self.Isc[idxs].mean(), IatVrbd.max()
                            )
                        else:
                            Icol, Vcol = self.Icell[idxs], self.Vcell[idxs]
                        IVcols.append([Icol, Vcol])
                    # append IVcols and continue
                    IVprev_cols.append(IVcols)
                    if prev_col:
                        # if circuits are same in both columns then continue
                        if not all(icol['crosstie'] == jcol['crosstie']
                                   for icol, jcol in zip(prev_col, col)):
                            # combine crosstied circuits
                            Iparallel, Vparallel = combine_parallel_circuits(
                                IVprev_cols, self.pvconst
                            )
                            IVall_cols.append([Iparallel, Vparallel])
                            # reset prev_col
                            prev_col = None
                            IVprev_cols = []
                            continue
                    # set prev_col and continue
                    prev_col = col
                # combine any remaining crosstied circuits in substring
                if not IVall_cols:
                    # combine crosstied circuits
                    Isub, Vsub = combine_parallel_circuits(
                        IVprev_cols, self.pvconst
                    )
                else:
                    Iparallel, Vparallel = zip(*IVall_cols)
                    Iparallel = np.asarray(Iparallel)
                    Vparallel = np.asarray(Vparallel)
                    Isub, Vsub = self.pvconst.calcParallel(
                        Iparallel, Vparallel, Vparallel.max(), Vparallel.min()
                    )
            bypassed = Vsub < self.Vbypass
            Vsub[bypassed] = self.Vbypass
            Isubstr.append(Isub)
            Vsubstr.append(Vsub)
            Isc_substr.append(np.interp(np.float64(0), Vsub, Isub))
            Imax_substr.append(Isub.max())
        Isubstr, Vsubstr = np.asarray(Isubstr), np.asarray(Vsubstr)
        Isc_substr = np.asarray(Isc_substr)
        Imax_substr = np.asarray(Imax_substr)
        Imod, Vmod = self.pvconst.calcSeries(
            Isubstr, Vsubstr, Isc_substr.mean(), Imax_substr.max()
        )
        Pmod = Imod * Vmod
        return Imod, Vmod, Pmod, Isubstr, Vsubstr

    def plotCell(self):
        """
        Plot cell I-V curves.
        Returns cellPlot : matplotlib.pyplot figure
        """
        cellPlot = plt.figure()
        plt.subplot(2, 2, 1)
        plt.plot(self.Vcell.T, self.Icell.T)
        plt.title('Cell Reverse I-V Characteristics')
        plt.ylabel('Cell Current, I [A]')
        plt.xlim(self.VRBD.min() - 1, 0)
        plt.ylim(0, self.Isc.mean() + 10)
        plt.grid()
        plt.subplot(2, 2, 2)
        plt.plot(self.Vcell.T, self.Icell.T)
        plt.title('Cell Forward I-V Characteristics')
        plt.ylabel('Cell Current, I [A]')
        plt.xlim(0, self.Voc.max())
        plt.ylim(0, self.Isc.mean() + 1)
        plt.grid()
        plt.subplot(2, 2, 3)
        plt.plot(self.Vcell.T, self.Pcell.T)
        plt.title('Cell Reverse P-V Characteristics')
        plt.xlabel('Cell Voltage, V [V]')
        plt.ylabel('Cell Power, P [W]')
        plt.xlim(self.VRBD.min() - 1, 0)
        plt.ylim((self.Isc.mean() + 10) * (self.VRBD.min() - 1), -1)
        plt.grid()
        plt.subplot(2, 2, 4)
        plt.plot(self.Vcell.T, self.Pcell.T)
        plt.title('Cell Forward P-V Characteristics')
        plt.xlabel('Cell Voltage, V [V]')
        plt.ylabel('Cell Power, P [W]')
        plt.xlim(0, self.Voc.max())
        plt.ylim(0, (self.Isc.mean() + 1) * self.Voc.max())
        plt.grid()
        return cellPlot

    def plotMod(self):
        """
        Plot module I-V curves.
        Returns modPlot : matplotlib.pyplot figure
        """
        modPlot = plt.figure()
        plt.subplot(2, 1, 1)
        plt.plot(self.Vmod, self.Imod)
        plt.title('Module I-V Characteristics')
        plt.ylabel('Module Current, I [A]')
        plt.ylim(ymin=0)
        plt.xlim(self.Vmod.min() - 1, self.Vmod.max() + 1)
        plt.grid()
        plt.subplot(2, 1, 2)
        plt.plot(self.Vmod, self.Pmod)
        plt.title('Module P-V Characteristics')
        plt.xlabel('Module Voltage, V [V]')
        plt.ylabel('Module Power, P [W]')
        plt.ylim(ymin=0)
        plt.xlim(self.Vmod.min() - 1, self.Vmod.max() + 1)
        plt.grid()
        return modPlot
