//! The Python bindings of the backend code written in Rust.
//!
//! This file holds only the bindings, which convert types and errors. The
//! logic stays in plain Rust modules that know nothing about Python.

mod greeting;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Build a greeting. The GIL is released while Rust runs.
#[pyfunction]
fn greet(py: Python<'_>, name: &str) -> PyResult<String> {
    py.detach(|| greeting::greet(name))
        .map_err(|error| PyValueError::new_err(error.to_string()))
}

#[pymodule]
fn assistant_rust(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(greet, module)?)
}
