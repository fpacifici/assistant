//! A toy module proving the path from Python to Rust end to end.

use std::fmt;

#[derive(Debug, PartialEq)]
pub struct EmptyName;

impl fmt::Display for EmptyName {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("name must not be empty")
    }
}

/// Builds a greeting for the given name.
pub fn greet(name: &str) -> Result<String, EmptyName> {
    if name.is_empty() {
        return Err(EmptyName);
    }
    Ok(format!("Hello, {name}!"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn greets_by_name() {
        assert_eq!(greet("Ada").as_deref(), Ok("Hello, Ada!"));
    }

    #[test]
    fn rejects_an_empty_name() {
        assert_eq!(greet(""), Err(EmptyName));
    }
}
