'''
   MFEM example 19

      This examples solves a quasi-static incompressible nonlinear
      elasticity problem of the form 0 = H(x), where H is an
      incompressible hyperelastic model and x is a block state vector
      containing displacement and pressure variables. 

      See c++ version in the MFEM library for more detail 

   Sample runs:
      python ex19.py -m ../data/beam-quad.mesh
      python ex19.py -m ../data/beam-tri.mesh
      python ex19.py -m ../data/beam-hex.mesh
      python ex19.py -m ../data/beam-tet.mesh

'''


import sys
from mfem.common.arg_parser import ArgParser
from mfem import path
import mfem.ser as mfem
from mfem.ser import intArray, add_vector, Add
from os.path import expanduser, join
import numpy as np
from numpy import sqrt, pi, cos, sin, hypot, arctan2
from scipy.special import erfc


parser = ArgParser(description='Ex10')
parser.add_argument('-m', '--mesh',
                    default = 'beam-quad.mesh', 
                    action = 'store', type = str,
                    help='Mesh file to use.')
parser.add_argument('-r', '--refine',
                    action = 'store', default = 2, type=int,
                    help = "Number of times to refine the mesh uniformly")
parser.add_argument('-o', '--order',
                    action = 'store', default = 2, type=int,
                    help = "Finite element order (polynomial degree)");
parser.add_argument('-rel', '--relative-tolerance',
                    action = 'store', default = 1e-4, type=float,
                    help = "Relative tolerance for the Newton solve.")
parser.add_argument('-abs', '--absolute-tolerance',
                    action = 'store', default = 1e-6, type=float,
                    help = "Absolute tolerance for the Newton solve.")
parser.add_argument("-it", "--newton-iterations",
                    action = 'store', default = 500, type=int,
                   "Maximum iterations for the Newton solve.");
parser.add_argument("-mu", "--shear-modulus",
                    action = 'store', default = 1.0, type=float,                    
                    help = "Shear modulus in the Neo-Hookean material.")
parser.add_argument('-vis', '--visualization',
                    action = 'store_true', default = True, 
                    help='Enable GLVis visualization')

args = parser.parse_args()

ref_levels = args.refine
order = args.order
visualization = args.visualization
mu = args.shear_modulus
newton_rel_tol = args.relative_tolelance
newton_abs_tol = args.absolute_tolelance
newton_iter = args.newton_iteration

parser.print_options(args)

meshfile = expanduser(join(path, 'data', args.mesh))
mesh = mfem.Mesh(meshfile, 1,1)
dim = mesh.Dimension()

for lev in range(ref_levels):
    mesh.UniformRefinement()
    
#  4. Define the shear modulus for the incompressible Neo-Hookean material
c_mu = mfem.ConstantCoefficient(mu)

#  5. Define the finite element spaces for displacement and pressure
#     (Taylor-Hood elements). By default, the displacement (u/x) is a second
#     order vector field, while the pressure (p) is a linear scalar function.
quad_coll = mfem.H1_FECollection(order, dim)
lin_coll =  mfem.H1_FECollection(order-1, dim)

R_space = mfem.FiniteElementSpace(mesh, quad_coll, dim, mfem.Ordering.byVDIM)
W_space = mfem.FiniteElementSpace(mesh, lin_coll)

spaces = [R_space W_space]
R_size = R_space.GetVSize()
W_size = W_space.GetVSize()

#   6. Define the Dirichlet conditions (set to boundary attribute 1 and 2)
ess_bdr_u = mfem.intArray(R_space.GetMesh()->bdr_attributes.Max())
ess_bdr_p = mfem.intArray(W_space.GetMesh()->bdr_attributes.Max())
ess_bdr_u.Assign(0)
ess_bdr_p.Assign(1)
ess_bdr = [ess_bdr_u, ess_bdr_p]


print("***********************************************************")
print("dim(R) = " + str(R_szie))
print("dim(W) = " + str(W_size))
print("dim(R+W) = " + str(R_size + W_size))
print("***********************************************************")

block_offsets = intArray([0, R_size, W_size])
block_offsets.PartialSum()

xp= mfem.BlockVector(block_offsets)

#  9. Define grid functions for the current configuration, reference
#     configuration, final deformation, and pressure
x_gf  = mfem.GridFunction(R_space)
x_ref = mfem.GridFunction(R_space)
x_def = mfem.GridFunction(R_space)
p_gf  = mfem.GridFunction(W_space)

x_gf.MakeRef(R_space, xp.GetBlock(0), 0)
p_gf.MakeRef(W_space, xp.GetBlock(1), 0)

deform = InitialDeformation(dim)
refconfig = ReferenceConfiguration(dim)

x_gf.ProjectCoefficient(deform)
x_ref.ProjectCoefficient(refconfig)
p_gf.Assign(0.0)

#  10. Initialize the incompressible neo-Hookean operator
oper = RubberOperator(spaces, ess_bdr, block_offsets,
                     newton_rel_tol, newton_abs_tol, newton_iter,
                     mu);
#  11. Solve the Newton system
oper.Solve(xp)

#  12. Compute the final deformation
mfem.subtract_vector(x_gf, x_ref, x_def)

#  13. Visualize the results if requested
if (visualization):    
    vis_u = mfem.socketstream("localhost", 19916)
    visualize(vis_u, mesh, x_gf, x_def, "Deformation", True)
    vis_p = mfem.socketstream("localhost", 19916)
    visualize(vis_p, mesh, x_gf, p_gf, "Deformation", True)
    
#  14. Save the displaced mesh, the final deformation, and the pressure
nodes = x
owns_nodes = 0
nodes, owns_nodes = mesh.SwapNodes(nodes, owns_nodes)

mesh.PrintToFile('deformed.mesh', 8)
p_gf.SaveToFile('pressure.sol', 8)
x_def.SaveToFile("defomrtaion.sol",  8)

'''
 Custom block preconditioner for the Jacobian of the incompressible nonlinear
 elasticity operator. It has the form

 P^-1 = [ K^-1 0 ][ I -B^T ][ I  0           ]
        [ 0    I ][ 0  I   ][ 0 -\gamma S^-1 ]

 where the original Jacobian has the form

 J = [ K B^T ]
     [ B 0   ]

 and K^-1 is an approximation of the inverse of the displacement part of the
 Jacobian and S^-1 is an approximation of the inverse of the Schur
 complement S = B K^-1 B^T. The Schur complement is approximated using
 a mass matrix of the pressure variables.
'''
class JacobianPreconditioner(mfem.Solver):
    def __init__(self, spaces, mass, offsets):
        self.pressure_mass = mass
        self.block_offsets = offsets
        super(JacobianPreconditioner, self).__init__(offsets)
        
        gamma = 0.00001;

        # The mass matrix and preconditioner do not change every Newton cycle, so we
        # only need to define them once
        self.mass_precs = self.GSSmoother(mass)

        mass_pcg_iter = mfem.CGSolver()
        mass_pcg.SetRelTol(1e-12)
        mass_pcg.SetAbsTol(1e-12)
        mass_pcg.SetMaxIter(200)
        mass_pcg.SetPrintLevel(0)
        mass_pcg.SetPreconditioner(self.mass_prec)
        mass_pcg.SetOperator(self.pressure_mass)
        mass_pcg.iterative_mode = False

        # The stiffness matrix does change every Newton cycle, so we will define it
        # during SetOperator
        self.stiff_pcg = None
        self.stiff_prec = None

    def Mult(self, k, y):
        # Extract the blocks from the input and output vectors
        disp_in = k[block_offsets[0]:block_offsets[1]]
        pres_in = k[block_offsets[1]:block_offsets[2]]        

        disp_out = y[block_offsets[0]:block_offsets[1]]
        pres_out = y[block_offsets[1]:block_offsets[2]]        

        temp  = mfem.Vector(block_offsets[1]-block_offsets[0])
        temp2 = mfem.Vector(block_offsets[1]-block_offsets[0])        

        # Perform the block elimination for the preconditioner
        self.mass_pcg-.Mult(pres_in, pres_out)
        pres_out *= -gamma

        self.jacobian.GetBlock(0,1).Mult(pres_out, temp)
        mfem.subtract_vector(disp_in, temp, temp2)
        self.stiff_pcg.Mult(temp2, disp_out)
        
    def SetOperator(op):
        self.jacobian = mfem.Opr2BlockOpr(op)
        if (self.stiff_prec == NULL)
            # Initialize the stiffness preconditioner and solver
            stiff_prec_gs = self.GSSmoother()
            self.stiff_prec = stiff_prec_gs

            stiff_pcg_iter = mfem.GMRESSolver()
            stiff_pcg_iter.SetRelTol(1e-8)
            stiff_pcg_iter.SetAbsTol(1e-8)
            stiff_pcg_iter.SetMaxIter(200)
            stiff_pcg_iter.SetPrintLevel(0)
            stiff_pcg_iter.SetPreconditioner(self.stiff_prec)
            stiff_pcg_iter.iterative_mode = False
            
            self.stiff_pcg = stiff_pcg_iter

        #  At each Newton cycle, compute the new stiffness preconditioner by updating
        #  the iterative solver which, in turn, updates its preconditioner
        self.stiff_pcg.SetOperator(jacobian.GetBlock(0,0))

class RubberOperator(mfem.PyOperator):
    def __init__(self, spaces, ess_bdr, block_offsets,
                       rel_tol, abs_tol, iter, mu):

        # Array<Vector *> -> tuple 
        self.rhs = (mfem.Vector(), mfem.Vector())
        self.rhs[0].Assgin(0)
        self.rhs[1].Assgin(0)
        
        self.spaces = spaces
        self.mu = mfem.ConstantCoefficient(mu)
        self.block_offsets = block_offsets

        Hform = mfem.BlockNonlinearForm(spaces)
        Hform.AddDomainIntegrator(mfem.IncompressibleNeoHookeanIntegrator(self.mu))
        Hform.SetEssentialBC(ess_bdr, self.rhs)
        self.Hform = Hform

        a = mfem.BilinearForm(self.spaces[0])
        one = mfem.ConstantCoefficient(1.0)
        a.AddDomainIntegrator(mfem.MassIntegrator(one))
        a.Assemble()
        a.Finalize()
        pressure_mass = a.LoseMat()

        self.j_prec = JacobianPreconditioner(spaces, pressure_mass, block_offsets)

        j_gmres = mfem.GMRESSolver()
        j_gmres.iterative_mode = False
        j_gmres.SetRelTol(1e-12)
        j_gmres.SetAbsTol(1e-12)
        j_gmres.SetMaxIter(300)
        j_gmres.SetPrintLevel(0)
        j_gmres.SetPreconditioner(self.j_prec)
        self.j_solver = j_gmres

        self.newton_solver = mfem.NewtonSolver()
        # Set the newton solve parameters
        newton_solver.iterative_mode = true;
        newton_solver.SetSolver(self.j_solver);
        newton_solver.SetOperator(self)
        newton_solver.SetPrintLevel(1)
        newton_solver.SetRelTol(rel_tol)
        newton_solver.SetAbsTol(abs_tol)
        newton_solver.SetMaxIter(iter)
        
    def Solve(xp):
        zero = mfem.Vector()
        self.newton_solver(zero, xp)
        if not newton_solver.GetConverged():
            assert False, "Newton Solver did not converge."

    def Mult(k, y):
        self.Hform.Mult(k, y)

    def GetGradient(xp):
        return Hform.GetGradient(xp)
        
        
#  Inline visualization
def visualize(out, mesh, deformed_nodes, field, field_name, init_vis):
    if out is None: return

    nodes = deformed_nodes
    owns_nodes = 0;

    nodes, owns_nodes = mesh.SwapNodes(nodes, owns_nodes)

    out.precision(8) 
    out.send_solution(mesh, field)   

    nodes, owns_nodes = mesh.SwapNodes(nodes, owns_nodes)

    if (init_vis):
      out.send_text("window_size 800 800")
      out.send_text( "window_title '"  + field_name)
      if (mesh.SpaceDimension() == 2):
         out.send_text("view 0 0")
         out.send_text("keys jlA")
      out.send_text("keys cm")         # show colorbar and mesh
      out.send_text("autoscale value") # update value-range; keep mesh-extents fixed
    out.flush()
   
#  FunctionCOefficient is wrapperd usng VectorPyCoefficient class
class InitialDeformation(mfem.VectorPyCoefficient):
   def EvalValue(self, x):
       y = x.copy()
       y[1] = x[1] + 0.25*x[0]
       return y
#  FunctionCOefficient is wrapperd usng VectorPyCoefficient class   
class ReferenceConfiguration(mfem.VectorPyCoefficient):
   def EvalValue(self, x):
       return y
   












