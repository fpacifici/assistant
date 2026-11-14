package greeting

import (
	"errors"
	"testing"
)

func TestGreetsByName(t *testing.T) {
	got, err := Greet("Ada")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "Hello, Ada!" {
		t.Errorf("got %q, want %q", got, "Hello, Ada!")
	}
}

func TestRejectsAnEmptyName(t *testing.T) {
	_, err := Greet("")
	if !errors.Is(err, ErrEmptyName) {
		t.Errorf("got %v, want ErrEmptyName", err)
	}
}
