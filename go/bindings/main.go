// Command bindings is the C ABI of the backend code written in Go. Built with
// -buildmode=c-shared it becomes libassistant_go.so, which Python loads with
// ctypes (see src/assistant/golib).
//
// This file holds only the bindings, which convert types and errors. The logic
// stays in plain Go packages that know nothing about C.
//
// Calling convention, shared by every exported function except AssistantFree:
//
//   - Strings go in as a pointer and a byte length, so they may hold NUL bytes.
//   - The function returns 0 on success and 1 on error. Either way it writes a
//     buffer allocated with C malloc to *out and its length to *outLen: the
//     result on success, the error message on error.
//   - The caller owns that buffer and releases it with AssistantFree.
//   - A panic on the calling goroutine is recovered and reported as an error.
package main

/*
#include <stdlib.h>
*/
import "C"

import (
	"fmt"
	"unsafe"

	"github.com/fpacifici/assistant/go/greeting"
)

// main is required by -buildmode=c-shared and never runs.
func main() {}

// AssistantFree releases a buffer returned by any exported function.
//
//export AssistantFree
func AssistantFree(buffer unsafe.Pointer) {
	C.free(buffer)
}

// AssistantGreet builds a greeting.
//
//export AssistantGreet
func AssistantGreet(name *C.char, nameLen C.size_t, out **C.char, outLen *C.size_t) C.int {
	return call(out, outLen, func() (string, error) {
		return greeting.Greet(C.GoStringN(name, C.int(nameLen)))
	})
}

// call runs fn and writes its result, or its error, to out per the calling
// convention above.
func call(out **C.char, outLen *C.size_t, fn func() (string, error)) (status C.int) {
	defer func() {
		if recovered := recover(); recovered != nil {
			status = write(out, outLen, fmt.Sprintf("panic: %v", recovered), 1)
		}
	}()
	result, err := fn()
	if err != nil {
		return write(out, outLen, err.Error(), 1)
	}
	return write(out, outLen, result, 0)
}

func write(out **C.char, outLen *C.size_t, value string, status C.int) C.int {
	*out = (*C.char)(C.CBytes([]byte(value)))
	*outLen = C.size_t(len(value))
	return status
}
