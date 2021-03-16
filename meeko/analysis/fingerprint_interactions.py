#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Meeko
#

import os

import numpy as np
import pandas as pd


atom_property_definitions = {'H': 'vdw', 'C': 'vdw', 'A': 'vdw', 'N': 'vdw', 'P': 'vdw', 'S': 'vdw',
                             'Br': 'vdw', 'I': 'vdw', 'F': 'vdw',
                             'NA': 'hb_acc', 'OA': 'hb_acc', 'SA': 'hb_acc', 'OS': 'hb_acc', 'NS': 'hb_acc', 
                             'HD': 'hb_don', 'HS': 'hb_don',
                             'Cl': 'non-metal', 
                             'Mg': 'metal', 'Ca': 'metal', 'Fe': 'metal', 'Zn': 'metal', 'Mn': 'metal',
                             'W': 'water',
                             'G0': 'glue', 'G1': 'glue', 'G2': 'glue', 'G3': 'glue', 
                             'CG0': 'glue', 'CG1': 'glue', 'CG2': 'glue', 'CG3': 'glue'}


def _compute_angle(v1, v2):
    unit_vector_1 = v1 / np.linalg.norm(v1)
    unit_vector_2 = v2 / np.linalg.norm(v2)
    dot_product = np.dot(unit_vector_1, unit_vector_2)
    angle = np.arccos(dot_product)
    return angle


def _is_valid_hydrogen_bond(atom_acc_1, atom_acc_2, atom_don_1, atom_don_2, hb_criteria, log=False):
    """Check if the hydrogen bond is valid based on the angles

    Donor-H -- acceptor angle        : atom_don_2-atom_don_1 -- atom_acc_1 (angle_1)
    Pre_acceptor-acceptor -- H angle : atom_acc_2-atom_acc_1 -- atom_don_1 (angle_2)

    Source: https://psa-lab.github.io/Hbind/user_guide/

    Args:
        atom_acc_1 (np.ndarray): coordinates of atom acceptor 1
        atom_acc_2 (np.ndarray): coordinates of atom acceptor 2
        atom_don_1 (np.ndarray): coordinates of atom donor 1
        atom_don_2 (np.ndarray): coordinates of atom donor 2
        hb_criteria (list): list a distance and two angles (in degrees) criteria to be satisfied

    Returns:
        bool: True if hydrogen bond is valid, otherwise False

    """
    distance = np.linalg.norm(atom_acc_1 - atom_don_2)

    if distance <= hb_criteria[0]:
        if atom_don_1 is not None and atom_acc_2 is not None:
            # atom_don_2-atom_don_1 -- atom_acc_1
            angle_1 = np.degrees(_compute_angle(atom_don_2 - atom_don_1, atom_acc_1 - atom_don_1))
            # atom_acc_2-atom_acc_1 -- atom_don_1
            angle_2 = np.degrees(_compute_angle(atom_acc_2 - atom_acc_1, atom_don_1 - atom_acc_1))
        elif atom_don_1 is None:
            # It means that there is no hydrogen atom, so then don atom is non-directional
            angle_1 = 180
            # atom_acc_2-atom_acc_1 -- atom_don_2
            angle_2 = np.degrees(_compute_angle(atom_acc_2 - atom_acc_1, atom_don_2 - atom_acc_1))
        elif atom_acc_2 is None:
            # It means that since there is no Pre_acceptor atom, so then acc atom is non-directional
            # atom_don_2-atom_don_1 -- atom_acc_1
            angle_1 = np.degrees(_compute_angle(atom_don_2 - atom_don_1, atom_acc_1 - atom_don_1))
            angle_2 = 180

        return (angle_1 >= hb_criteria[1]) & (angle_2 >= hb_criteria[2])
    else:
        return False


class FingerprintInteractions:

    def __init__(self, receptor):
        """FingerprintInteractions object

        Args:
            receptor (PDBQTReceptor): receptor 

        """
        self._data = []
        self._max_distance = 4.2
        self._unique_interactions = {'hb': {*()},
                                     'vdw': {*()},
                                     'water': {*()},
                                     'reactive': {*()}}
        self._criteria = {'hb_acc': [3.2, 120, 90], 'hb_don': [3.2, 120, 90],
                          'all': [4.2], 'vdw': [4.2],
                          'water': [3.2, 120, 90],
                          'reactive': [2.0]}

        self._receptor = receptor

    def run(self, molecules):
        """Run the fingerprint interactions.
        
        Args:
            molecules (PDBQTMolecule, list of PDBQTMolecule): molecule or list of molecules

        """
        data = []

        if not isinstance(molecules, (list, tuple)):
            molecules = [molecules]

        for molecule in molecules:
            has_flexible_residues = molecule.has_flexible_residues()

            for pose in molecule:
                tmp_hb = []
                tmp_vdw = []
                tmp_water = []

                lig_atoms = pose.atoms_by_properties(['ligand'])
                if pose.has_water_molecules():
                    # Because water molecules are considered as separate entities like flexible residues
                    lig_atoms = np.hstack((lig_atoms, pose.atoms_by_properties(['water'])))

                for lig_atom in lig_atoms:
                    # Get rigid part of the receptor
                    rec_rigid_atoms = self._receptor.closest_atoms_from_positions(lig_atom['xyz'], self._max_distance)
                    rec_rigid_flex = [self._receptor]
                    rec_rigid_flex_atoms = [rec_rigid_atoms]

                    # Get the flexible part of the receptor (if present)
                    if has_flexible_residues:
                        rec_flex_atoms = pose.closest_atoms_from_positions(lig_atom['xyz'], self._max_distance, ['flexible_residue'])
                        rec_rigid_flex.append(pose)
                        rec_rigid_flex_atoms.append(rec_flex_atoms)

                    # Get ligand atom property
                    lig_atom_property = atom_property_definitions[lig_atom['atom_type']]

                    # If the atom is hb_acc or hb_don, we will need to define the hb vector for that atom
                    if lig_atom_property in ['hb_acc', 'hb_don']:
                        lig_bound_atoms_index = pose.neighbor_atoms(lig_atom['idx'])
                        lig_bound_atoms = pose.atoms(lig_bound_atoms_index[0])
                        lig_hb_vector = np.mean(lig_bound_atoms['xyz'], axis=0)

                    for rec, rec_atoms in zip(rec_rigid_flex, rec_rigid_flex_atoms):
                        if rec_atoms.size > 0:
                            for rec_atom in rec_atoms:
                                # And we do the same for the receptor
                                rec_atom_property = atom_property_definitions[rec_atom['atom_type']]

                                if rec_atom_property in ['hb_acc', 'hb_don']:
                                    rec_bound_atoms_index = rec.neighbor_atoms(rec_atom['idx'])
                                    rec_bound_atoms = rec.atoms(rec_bound_atoms_index[0])
                                    rec_hb_vector = np.mean(rec_bound_atoms['xyz'], axis=0)

                                if lig_atom_property == 'vdw' and rec_atom_property == 'vdw':
                                    # vdW - vdW interaction
                                    tmp_vdw.append('v_%s:%d' % (rec_atom['chain'], rec_atom['resid']))
                                elif lig_atom_property == 'hb_don' and rec_atom_property == 'hb_acc':
                                    # (LIG) HB donor - HB acceptor (REC) interaction
                                    good_hb = _is_valid_hydrogen_bond(rec_atom['xyz'], rec_hb_vector,
                                                                      lig_atom['xyz'], lig_hb_vector,
                                                                      self._criteria[lig_atom_property])

                                    if good_hb:
                                        chain, resid, name = rec_atom['chain'], rec_atom['resid'], rec_atom['name']
                                        tmp_hb.append('h_%s:%d:%s' % (chain, resid, name))
                                elif lig_atom_property == 'hb_acc' and rec_atom_property == 'hb_don':
                                    # (LIG) HB acceptor - HB donor (REC) interaction
                                    good_hb = _is_valid_hydrogen_bond(lig_atom['xyz'], lig_hb_vector,
                                                                      rec_atom['xyz'], rec_hb_vector,
                                                                      self._criteria[lig_atom_property])

                                    if good_hb:
                                        chain, resid, name = rec_atom['chain'], rec_atom['resid'], rec_atom['name']
                                        tmp_hb.append('h_%s:%d:%s' % (chain, resid, name))
                                elif lig_atom_property == 'water':
                                    good_hb = False

                                    if rec_atom_property == 'hb_don':
                                        # (LIG) W acceptor - HB donor (REC) interaction
                                        good_hb = _is_valid_hydrogen_bond(lig_atom['xyz'], None,
                                                                          rec_atom['xyz'], rec_hb_vector,
                                                                          self._criteria[lig_atom_property])
                                    elif rec_atom_property == 'hb_acc':
                                        # (LIG) W donor - HB acceptor (REC) interaction
                                        good_hb = _is_valid_hydrogen_bond(rec_atom['xyz'], rec_hb_vector,
                                                                          None, lig_atom['xyz'],
                                                                          self._criteria[lig_atom_property])

                                    if good_hb:
                                        tmp_water.append('w_%s:%d' % (rec_atom['chain'], rec_atom['resid']))
                                else:
                                    pass

                tmp_hb = set(tmp_hb)
                tmp_vdw = set(tmp_vdw)
                tmp_water = set(tmp_water)
                # Store all the unique interactions we seen
                self._unique_interactions['hb'].update(tmp_hb)
                self._unique_interactions['vdw'].update(tmp_vdw)
                self._unique_interactions['water'].update(tmp_water)

                data.append((pose.name, pose.pose_id, list(tmp_hb), list(tmp_vdw), list(tmp_water)))

        self._data.extend(data)

    def to_dataframe(self):
        """Generate a panda DataFrame with all the interactions

        Returns:
            pd.DataFrame: pandas DataFrame containing all the interaction 
                found between the molecules and the receptor

        """
        count = 0
        resid_to_idx_encoder = {}
        columns = [[], []]
        names = []
        poses = []

        # Generate one-hot encoder-like (and the columns for the dataframe)
        for inte_type, resids in self._unique_interactions.items():
            columns[0].extend([inte_type] * len(resids))
            # Remove the v/w/h_ tag for the column names
            columns[1].extend([resid[2:] for resid in resids])

            for resid in resids:
                resid_to_idx_encoder[resid] = count
                count += 1

        # Create multicolumns for the dataframe
        c_tuples = list(zip(*columns))
        multi_columns = pd.MultiIndex.from_tuples(c_tuples)

        # Convert resids in one hot fingerprint interactions
        fpi = np.zeros(shape=(len(self._data), count), dtype=int)

        for i, pose_molecule in enumerate(self._data):
            idx = [resid_to_idx_encoder[x] for x in pose_molecule[2] + pose_molecule[3] + pose_molecule[4]]
            fpi[i][idx] = 1
            names.append(pose_molecule[0])
            poses.append(pose_molecule[1] + 1)

        # Create final dataframe
        df = pd.DataFrame(fpi, index=np.arange(0, len(self._data)), columns=multi_columns)
        # Remove columns where there are zero interactions. This is because we mix hb + water interactions.
        df = df.loc[:, (df.sum(axis=0) != 0)]
        df['name'] = names
        df['pose'] = poses
        df.set_index(['name', 'pose'], inplace=True)

        return df
