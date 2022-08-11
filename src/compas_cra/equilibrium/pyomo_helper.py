#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Some functions to help building pyomo optimisation problems
"""

import pyomo.environ as pyo

from pyomo.core.base.matrix_constraint import MatrixConstraint


__author__ = "Gene Ting-Chun Kao"
__email__ = "kao@arch.ethz.ch"

__all__ = ['initialisations',
           'bounds',
           'objectives',
           'constraints',
           'equilibrium_setup',
           'static_equilibrium_constraints',
           'pyomo_result_assembly']


def initialisations(
    variable: str = 'f_tilde',
):
    """Variable initialisations for pyomo.

        Parameters
        ----------
        variable : str, optional
            * f_tilde: force, :math:`f ̃ = ({f_n}^+, {f_n}^-, f_u, f_v)`

        Returns
        -------
        initialisations function for pyomo

    """
    def f_tilde_init(model, i):
        """initialise f ̃ with [1, 0, 1, 1]"""
        if i % 4 == 1:
            return 0.0
        return 1.0

    if variable == 'f_tilde':
        return f_tilde_init


def bounds(
    variable: str = 'd',
    d_bnd: float = 1e-3
):
    r"""Variable bounds for pyomo.

        Parameters
        ----------
        variable : str, optional
            * d: virtual displacement :math:`\delta d`
            * f: force, :math:`f = (f_n, f_u, f_v)`
            * f_tilde: force, :math:`f ̃ = ({f_n}^+, {f_n}^-, f_u, f_v)`
        d_bnd : float, optional
            displacement bounds, -d_bnd <= d <= d_bnd

        Returns
        -------
        bounds constraint/domain function for pyomo

    """
    def f_tilde_bnds(model, i):
        """bounds of f ̃, f ̃ include [fn+, fn-, fu, fv]"""
        if i % 4 == 0 or i % 4 == 1:
            return pyo.NonNegativeReals
        return pyo.Reals

    def f_bnds(model, i):
        """bounds of f, f include [fn, fu, fv]"""
        if i % 3 == 0:
            return pyo.NonNegativeReals
        return pyo.Reals

    def d_bnds(model, i):
        return (-d_bnd, model.d[i], d_bnd)

    if variable == 'f':
        return f_bnds
    if variable == 'f_tilde':
        return f_tilde_bnds
    if variable == 'd':
        return d_bnds


def objectives(
    solver: str = 'cra',
    weights: tuple = (1e+0, 1e+0, 1e+6)
):
    """Objective functions for pyomo.

        Parameters
        ----------
        solver : str, optional
            * cra: CRA objective, :math:`W_{compression} * ||f_n||_2^2 + W_{α} * ||α||_2^2`
            * cra_penalty: CRA penalty objective, :math:`W_{compression} * ||{f_n}^+||_2^2 + W_{tension} * ||{f_n}^-||_2^2 + W_{α} * ||α||_2^2`
            * rbe: RBE objective, :math:`W_{compression} * ||{f_n}^+||_2^2 + W_{tension} * ||{f_n}^-||_2^2`
        weights : tuple, optional
            weighting factors, :math:`(W_{α}, W_{compression}, W_{tension})`

        Returns
        -------
        objective function for pyomo

    """

    def obj_rbe(model):
        """RBE objective function"""
        return _obj_weights(model)

    def obj_cra(model):
        """CRA objective function"""
        alpha_sum = pyo.dot_product(model.alpha, model.alpha)
        f_sum = 0
        for i in model.f_id:
            if i % 3 == 0:
                f_sum = f_sum + (model.f[i] * model.f[i])
        return f_sum + alpha_sum

    def obj_cra_penalty(model):
        """CRA penalty objective function"""
        alpha_sum = pyo.dot_product(model.alpha, model.alpha) * weights[0]  # alpha
        f_sum = _obj_weights(model)
        return alpha_sum + f_sum

    def _obj_weights(model):
        f_sum = 0
        for i in model.f_id:
            if i % 4 == 1:
                f_sum = f_sum + (model.f[i] * model.f[i] * weights[2])  # tension
            elif i % 4 == 0:
                f_sum = f_sum + (model.f[i] * model.f[i] * weights[1])  # compression
        return f_sum

    if solver == 'cra':
        return obj_cra
    if solver == 'cra_penalty':
        return obj_cra_penalty
    if solver == 'rbe':
        return obj_rbe


def constraints(
    name: str = 'contact',
    eps: float = 1e-4
):
    r"""Constraint functions for pyomo.

        Parameters
        ----------
        name : str, optional
            * contact: contact constraint, :math:`{f_{jkn}^i}\: ({\delta d_{jkn}^i} + eps) = 0`
            * penalty_contact: penalty formulation contact constraint, :math:`{f_{jkn}^{i+}}\:({\delta d_{jkn}^i} + eps) = 0`
            * fn_np: fn+ and fn- cannot coexist, :math:`{f_{jkn}^{i+}} \: {f_{jkn}^{i-}} = 0`
            * no_penetration: no penetration constraint, :math:`{f_{jkn}^{i+}}\:({\delta d_{jkn}^i} + eps) = 0`
            * ft_dt: friction and virtual sliding alignment, :math:`f_{jkt}^{i} = -{α_{jk}^i} \: \delta{d}_{jkt}^{i}`
            * penalty_ft_dt: penalty formulation friction and virtual sliding alignment, :math:`f_{jkt}^{i} = -{α_{jk}^i} \: \delta{d}_{jkt}^{i}`
        eps : float, optional
            epsilon, overlapping parameter

        Returns
        -------
        constraint function for pyomo

    """

    def contact_con(model, i):
        """contact constraint"""
        dn = model.d[i * 3]
        fn = model.f[i * 3]
        return ((dn + eps) * fn, 0)

    def penalty_contact_con(model, i):
        """penalty formulation contact constraint"""
        dn = model.d[i * 3]
        fn = model.f[i * 4]
        return ((dn + eps) * fn, 0)

    def fn_np_con(model, i):
        """fn+ and fn- cannot coexist constraints"""
        return (model.f[i * 4] * model.f[i * 4 + 1], 0)

    def no_penetration_con(m, t):
        """no penetration constraint"""
        return (0, m.d[t * 3] + eps, None)

    def ft_dt_con(model, i, xyz):
        """friction and virtual sliding alignment"""
        d_t = model.displs[i * 3 + 1] + model.displs[i * 3 + 2]
        f_t = model.forces[i * 3 + 1] + model.forces[i * 3 + 2]
        return (f_t[xyz], -d_t[xyz] * model.alpha[i])

    def penalty_ft_dt_con(model, i, xyz):
        """penalty formulation friction and virtual sliding alignment"""
        d_t = model.displs[i * 3 + 1] + model.displs[i * 3 + 2]
        f_t = model.forces[i * 4 + 2] + model.forces[i * 4 + 3]
        return (f_t[xyz], -d_t[xyz] * model.alpha[i])

    if name == 'contact':
        return contact_con
    if name == 'penalty_contact':
        return penalty_contact_con
    if name == 'fn_np':
        return fn_np_con
    if name == 'no_penetration':
        return no_penetration_con
    if name == 'ft_dt':
        return ft_dt_con
    if name == 'penalty_ft_dt':
        return penalty_ft_dt_con


def equilibrium_setup(assembly):
    """set up equilibrium matrix"""
    from compas_cra.equilibrium.cra_helper import make_aeq

    num_nodes = assembly.graph.number_of_nodes()
    key_index = {key: index for index, key in enumerate(assembly.graph.nodes())}

    fixed = [key for key in assembly.graph.nodes_where({'is_support': True})]
    fixed = [key_index[key] for key in fixed]
    free = list(set(range(num_nodes)) - set(fixed))

    aeq, vcount = make_aeq(assembly)
    aeq = aeq[[index * 6 + i for index in free for i in range(6)], :]
    print("Aeq: ", aeq.shape)

    return aeq, vcount, free


def static_equilibrium_constraints(model, assembly, aeq, vcount, free, density, mu):
    """create equilibrium and friction constraints"""
    import numpy as np
    from compas_cra.equilibrium.cra_helper import make_afr

    num_nodes = assembly.graph.number_of_nodes()
    key_index = {key: index for index, key in enumerate(assembly.graph.nodes())}

    p = [[0, 0, 0, 0, 0, 0] for i in range(num_nodes)]
    for node in assembly.graph.nodes():
        block = assembly.node_block(node)
        index = key_index[node]
        p[index][2] = -block.volume() * density

    p = np.array(p, dtype=float)
    p = p[free, :].reshape((-1, 1), order='C')

    afr = make_afr(vcount, fcon_number=8, mu=mu)
    print("Afr: ", afr.shape)

    equilibrium_constraints = MatrixConstraint(aeq.data, aeq.indices, aeq.indptr,
                                               -p.flatten(), -p.flatten(), model.array_f)

    friction_constraint = MatrixConstraint(afr.data, afr.indices, afr.indptr,
                                           [None for i in range(afr.shape[0])],
                                           np.zeros(afr.shape[0]), model.array_f)
    return equilibrium_constraints, friction_constraint


def pyomo_result_assembly(model, assembly, penalty=False, verbose=False):
    """Save pyomo optimisation results to assembly."""

    shift = 4  # for cra_penalty and rbe shift number is 4
    if not penalty:
        shift = 3

    # save force to assembly
    offset = 0
    for edge in assembly.graph.edges():
        interfaces = assembly.graph.edge_attribute(edge, 'interfaces')
        for interface in interfaces:
            interface.forces = []
            n = len(interface.points)
            for i in range(n):
                interface.forces.append({
                    'c_np': model.f[offset + shift * i + 0].value,
                    'c_nn': model.f[offset + shift * i + 1].value if shift == 4 else 0,
                    'c_u': model.f[offset + shift * i + 1 + (1 if shift == 4 else 0)].value,
                    'c_v': model.f[offset + shift * i + 2 + (1 if shift == 4 else 0)].value
                })
            offset += shift * n

    # save displacement to assembly
    if model.find_component('q') is not None:
        q = [model.q[i].value for i in range(len(model.q))]
        if verbose:
            print("q:", q)
        offset = 0
        for node in assembly.graph.nodes():
            if assembly.graph.node_attribute(node, 'is_support'):
                continue
            displacement = q[offset:offset + 6]
            assembly.graph.node_attribute(node, 'displacement', displacement)
            offset += 6
