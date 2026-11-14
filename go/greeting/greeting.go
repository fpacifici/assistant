// Package greeting is a toy module proving the path from Python to Go end to end.
package greeting

import "errors"

// ErrEmptyName is returned when Greet is called without a name.
var ErrEmptyName = errors.New("name must not be empty")

// Greet builds a greeting for the given name.
func Greet(name string) (string, error) {
	if name == "" {
		return "", ErrEmptyName
	}
	return "Hello, " + name + "!", nil
}
