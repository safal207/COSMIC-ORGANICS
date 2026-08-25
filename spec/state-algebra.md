# State Algebra v0.1

**Status:** HYPOTHESIS

State Algebra gives mathematical meaning to the informal operations “add, multiply, subtract, divide” when discussing material states.

Let a state be a vector:

\[
M=(x_A,x_M,x_C,p_1,\ldots,p_n)
\]

with phase fractions `x_A + x_M + x_C = 1` when a mixture representation is used.

## Composition: `A ⊕ B`

Composition combines states or phases under a declared mixture rule.

\[
M = \alpha A \oplus (1-\alpha)B
\]

The operator is not assumed to be simple arithmetic averaging for every physical property.

## Interaction: `A ⊗ B`

Interaction represents a coupling term that exists because states coexist or influence one another.

A minimal dimensionless interaction descriptor is:

\[
I(A,B)=x_Ax_B
\]

This is a descriptor, not a universal physical law. Real interface behavior depends on morphology, geometry, kinetics, chemistry, and scale.

## Difference: `B ⊖ A`

Difference measures a transition:

\[
\Delta M = M_{after}-M_{before}
\]

It can be applied component-wise to observables or structural descriptors.

## Ratio: `A ⊘ B`

Ratio is valid for compatible nonzero scalar observables:

\[
R_p = p(A)/p(B)
\]

The operator is undefined when units or semantics are incompatible.

## Transition operator

The central operator is not arithmetic but transformation:

\[
\Phi: (M_t,U_t) \mapsto M_{t+1}
\]

State Algebra therefore treats computation primarily as **composition of transitions**:

\[
\Phi_n \circ \dots \circ \Phi_2 \circ \Phi_1(M_0)=M_n
\]

## Algebraic discipline

No operator is physically meaningful without declaring:

1. operands and units;
2. state representation;
3. interaction model;
4. boundary conditions;
5. scale;
6. validation target.
