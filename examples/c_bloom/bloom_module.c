#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "bloom.h"

typedef struct {
    PyObject_HEAD
    BloomFilter *filter;
} PyBloomFilter;

static void PyBloomFilter_dealloc(PyBloomFilter *self) {
    bloom_free(self->filter);
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static int PyBloomFilter_init(PyBloomFilter *self, PyObject *args, PyObject *kwds) {
    size_t size, expected, hash_count = 0;
    static char *kwlist[] = {"size", "expected_elements", "hash_count", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "KK|K", kwlist, &size, &expected, &hash_count))
        return -1;
    self->filter = bloom_init(size, expected, hash_count);
    if (!self->filter) {
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate BloomFilter");
        return -1;
    }
    return 0;
}

static PyObject* PyBloomFilter_add(PyBloomFilter *self, PyObject *arg) {
    const char *buf;
    Py_ssize_t len;

    if (PyUnicode_Check(arg)) {
        PyObject *utf8 = PyUnicode_AsUTF8String(arg);
        if (!utf8) return NULL;
        buf = PyBytes_AsString(utf8);
        len = PyBytes_Size(utf8);
        bloom_add(self->filter, buf, len);
        Py_DECREF(utf8);
    } else if (PyBytes_Check(arg)) {
        buf = PyBytes_AsString(arg);
        len = PyBytes_Size(arg);
        bloom_add(self->filter, buf, len);
    } else {
        PyErr_SetString(PyExc_TypeError, "Expected str or bytes");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject* PyBloomFilter_exists(PyBloomFilter *self, PyObject *arg) {
    const char *buf;
    Py_ssize_t len;

    if (PyUnicode_Check(arg)) {
        PyObject *utf8 = PyUnicode_AsUTF8String(arg);
        if (!utf8) return NULL;
        buf = PyBytes_AsString(utf8);
        len = PyBytes_Size(utf8);
        int res = bloom_exists(self->filter, buf, len);
        Py_DECREF(utf8);
        return PyBool_FromLong(res);
    } else if (PyBytes_Check(arg)) {
        buf = PyBytes_AsString(arg);
        len = PyBytes_Size(arg);
        return PyBool_FromLong(bloom_exists(self->filter, buf, len));
    } else {
        PyErr_SetString(PyExc_TypeError, "Expected str or bytes");
        return NULL;
    }
}

static PyObject* PyBloomFilter_clear(PyBloomFilter *self) {
    bloom_clear(self->filter);
    Py_RETURN_NONE;
}

static PyObject* PyBloomFilter_estimated_fpr(PyBloomFilter *self) {
    return PyFloat_FromDouble(bloom_estimated_false_positive_rate(self->filter));
}

static PyObject* PyBloomFilter_get_hash_count(PyBloomFilter *self) {
    return PyLong_FromSize_t(bloom_get_hash_count(self->filter));
}

static PyObject* PyBloomFilter_get_indices(PyBloomFilter *self, PyObject *arg) {
    const char *buf;
    Py_ssize_t len;
    if (PyUnicode_Check(arg)) {
        PyObject *utf8 = PyUnicode_AsUTF8String(arg);
        if (!utf8) return NULL;
        buf = PyBytes_AsString(utf8);
        len = PyBytes_Size(utf8);
        size_t *indices = (size_t*)malloc(self->filter->hash_count * sizeof(size_t));
        if (!indices) {
            PyErr_SetString(PyExc_MemoryError, "Out of memory");
            Py_DECREF(utf8);
            return NULL;
        }
        bloom_get_indices(self->filter, buf, len, indices);
        PyObject *list = PyList_New(self->filter->hash_count);
        for (size_t i = 0; i < self->filter->hash_count; i++)
            PyList_SET_ITEM(list, i, PyLong_FromSize_t(indices[i]));
        free(indices);
        Py_DECREF(utf8);
        return list;
    } else if (PyBytes_Check(arg)) {
        buf = PyBytes_AsString(arg);
        len = PyBytes_Size(arg);
        size_t *indices = (size_t*)malloc(self->filter->hash_count * sizeof(size_t));
        if (!indices) {
            PyErr_SetString(PyExc_MemoryError, "Out of memory");
            return NULL;
        }
        bloom_get_indices(self->filter, buf, len, indices);
        PyObject *list = PyList_New(self->filter->hash_count);
        for (size_t i = 0; i < self->filter->hash_count; i++)
            PyList_SET_ITEM(list, i, PyLong_FromSize_t(indices[i]));
        free(indices);
        return list;
    } else {
        PyErr_SetString(PyExc_TypeError, "Expected str or bytes");
        return NULL;
    }
}

static PyMethodDef PyBloomFilter_methods[] = {
    {"add", (PyCFunction)PyBloomFilter_add, METH_O, "Add element"},
    {"exists", (PyCFunction)PyBloomFilter_exists, METH_O, "Check element"},
    {"clear", (PyCFunction)PyBloomFilter_clear, METH_NOARGS, "Clear filter"},
    {"estimated_fpr", (PyCFunction)PyBloomFilter_estimated_fpr, METH_NOARGS, "Estimated false positive rate"},
    {"get_hash_count", (PyCFunction)PyBloomFilter_get_hash_count, METH_NOARGS, "Number of hash functions"},
    {"get_indices", (PyCFunction)PyBloomFilter_get_indices, METH_O, "Get hashed indices"},
    {NULL}
};

static PyTypeObject PyBloomFilterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bloom.BloomFilter",
    .tp_basicsize = sizeof(PyBloomFilter),
    .tp_itemsize = 0,
    .tp_dealloc = (destructor)PyBloomFilter_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = "BloomFilter objects",
    .tp_methods = PyBloomFilter_methods,
    .tp_init = (initproc)PyBloomFilter_init,
    .tp_new = PyType_GenericNew,
};

static struct PyModuleDef bloommodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "bloom",
    .m_doc = "Bloom filter C extension",
    .m_size = -1,
};

PyMODINIT_FUNC PyInit_bloom(void) {
    PyObject *m;
    if (PyType_Ready(&PyBloomFilterType) < 0) return NULL;
    m = PyModule_Create(&bloommodule);
    if (!m) return NULL;
    Py_INCREF(&PyBloomFilterType);
    PyModule_AddObject(m, "BloomFilter", (PyObject*)&PyBloomFilterType);
    return m;
}
