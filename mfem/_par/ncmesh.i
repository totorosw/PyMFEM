%module(package="mfem._par") ncmesh

%feature("autodoc", "1");

%{
#include <fstream>
#include <iostream>
  
#include "io_stream.hpp"         
#include "mesh/ncmesh.hpp"
#include "numpy/arrayobject.h"      
%}

%init %{
import_array();
%}

%include "exception.i"
%import "mesh.i"
%import "array.i"
%import "fem/geom.hpp"
%import "../common/exception.i"

%import "../common/io_stream_typemap.i"
OSTREAM_TYPEMAP(std::ostream&)

%immutable embeddings;
%include  "mesh/ncmesh.hpp"

 /*
  void PrintVertexParents(std::ostream &out) const;
  void PrintCoarseElements(std::ostream &out) const;
  void PrintStats(std::ostream &out = mfem::out) const;
 */

#ifndef SWIGIMPORTED
OSTREAM_ADD_DEFAULT_STDOUT_FILE(NCMesh, PrintVertexParents)
OSTREAM_ADD_DEFAULT_STDOUT_FILE(NCMesh, PrintCoarseElements)
OSTREAM_ADD_DEFAULT_FILE(NCMesh, PrintStats)
#endif
