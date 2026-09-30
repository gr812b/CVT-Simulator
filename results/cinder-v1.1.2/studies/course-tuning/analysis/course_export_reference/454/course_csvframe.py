"""Tiny CSV/DataFrame compatibility layer for frozen figure exporters.

Implements only the pandas surface used by the recovered Section 4.5 plotters.
It depends only on the Python standard library and NumPy, both present in the
frozen CINDER results environment. It is not a general pandas replacement.
"""
from __future__ import annotations
import csv
import re
from collections import namedtuple
from pathlib import Path
import numpy as np

__version__ = "cinder-csvframe-1"


def _as_array(value):
    return value._data if isinstance(value, Series) else np.asarray(value)


def _parse_column(values):
    out=[]
    numeric=True
    for v in values:
        if v in ("", None):
            out.append(np.nan)
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            numeric=False
            break
    if numeric:
        return np.asarray(out,dtype=float)
    return np.asarray(["" if v is None else str(v) for v in values],dtype=str)


class _StringMethods:
    def __init__(self, series): self._s=series
    def contains(self, pattern, regex=True):
        vals=self._s._data.astype(str)
        if regex:
            r=re.compile(pattern)
            data=np.asarray([bool(r.search(v)) for v in vals],dtype=bool)
        else:
            data=np.asarray([pattern in v for v in vals],dtype=bool)
        return Series(data,self._s.index)


class _SeriesILoc:
    def __init__(self,s): self.s=s
    def __getitem__(self,key): return self.s._data[key]


class Series:
    __array_priority__=1000
    def __init__(self,data,index=None,name=None):
        self._data=np.asarray(data)
        self.index=np.arange(len(self._data)) if index is None else np.asarray(index)
        self.name=name
    def __array__(self,dtype=None): return np.asarray(self._data,dtype=dtype)
    def __len__(self): return len(self._data)
    def __iter__(self): return iter(self._data)
    def __getitem__(self,key):
        if isinstance(key,str): raise TypeError("Series keys are positional in this compact layer")
        return self._data[key]
    @property
    def iloc(self): return _SeriesILoc(self)
    @property
    def str(self): return _StringMethods(self)
    @property
    def is_monotonic_increasing(self):
        if len(self._data)<2: return True
        try: return bool(np.all(np.diff(self._data.astype(float))>=0))
        except Exception: return bool(all(a<=b for a,b in zip(self._data[:-1],self._data[1:])))
    def astype(self,dtype): return Series(self._data.astype(dtype),self.index,self.name)
    def copy(self): return Series(self._data.copy(),self.index.copy(),self.name)
    def eq(self,x): return Series(self._data==x,self.index)
    def le(self,x): return Series(self._data<=x,self.index)
    def ge(self,x): return Series(self._data>=x,self.index)
    def between(self,a,b): return Series((self._data>=a)&(self._data<=b),self.index)
    def where(self,mask):
        m=np.asarray(_as_array(mask),dtype=bool)
        if np.issubdtype(self._data.dtype,np.number): out=self._data.astype(float,copy=True)
        else: out=self._data.astype(object,copy=True)
        out[~m]=np.nan
        return Series(out,self.index,self.name)
    def abs(self): return Series(np.abs(self._data),self.index,self.name)
    def idxmin(self):
        a=np.asarray(self._data,dtype=float); return self.index[int(np.nanargmin(a))]
    def min(self): return np.nanmin(self._data.astype(float)) if np.issubdtype(self._data.dtype,np.number) else min(self._data)
    def max(self): return np.nanmax(self._data.astype(float)) if np.issubdtype(self._data.dtype,np.number) else max(self._data)
    def all(self): return bool(np.all(self._data))
    def any(self): return bool(np.any(self._data))
    def sum(self): return np.sum(self._data)
    def to_frame(self): return _RowFrameFromSeries(self)
    def _bin(self,other,op): return Series(op(self._data,_as_array(other)),self.index,self.name)
    def __and__(self,o): return self._bin(o,np.logical_and)
    def __or__(self,o): return self._bin(o,np.logical_or)
    def __add__(self,o): return self._bin(o,np.add)
    def __radd__(self,o): return Series(np.add(o,self._data),self.index,self.name)
    def __sub__(self,o): return self._bin(o,np.subtract)
    def __rsub__(self,o): return Series(np.subtract(o,self._data),self.index,self.name)
    def __mul__(self,o): return self._bin(o,np.multiply)
    def __rmul__(self,o): return Series(np.multiply(o,self._data),self.index,self.name)
    def __truediv__(self,o): return self._bin(o,np.divide)
    def __rtruediv__(self,o): return Series(np.divide(o,self._data),self.index,self.name)
    def __neg__(self): return Series(-self._data,self.index,self.name)


class Row:
    def __init__(self,columns,values,label=None):
        self._columns=list(columns); self._values=dict(zip(columns,values)); self.name=label
    def __getitem__(self,key): return self._values[key]
    def __setitem__(self,key,value): self._values[key]=value
    def __getattr__(self,key):
        if key in self._values:return self._values[key]
        raise AttributeError(key)
    def copy(self): return Row(self._columns,[self._values[c] for c in self._columns],self.name)
    def to_frame(self): return _RowFrame(self)


class _RowFrame:
    def __init__(self,row): self.row=row
    @property
    def T(self):
        return DataFrame({c:np.asarray([self.row._values[c]]) for c in self.row._columns},index=np.asarray([self.row.name if self.row.name is not None else 0]))


class _RowFrameFromSeries:
    # Only retained for completeness; recovered scripts call Row.to_frame().
    def __init__(self,s): self.s=s
    @property
    def T(self): return DataFrame({str(self.s.name or 0):self.s._data},index=self.s.index)


class _DataFrameILoc:
    def __init__(self,df):self.df=df
    def __getitem__(self,key):
        if isinstance(key,(int,np.integer)):
            pos=key if key>=0 else len(self.df)+key
            return self.df._row_at(pos)
        raise TypeError("Only scalar iloc is required by the frozen figure exporters")


class _DataFrameLoc:
    def __init__(self,df):self.df=df
    def __getitem__(self,key):
        if isinstance(key,Series) or (isinstance(key,np.ndarray) and key.dtype==bool) or isinstance(key,list):
            arr=np.asarray(_as_array(key))
            if arr.dtype==bool:return self.df._filter(arr)
        # Scalar label lookup.
        hits=np.flatnonzero(self.df.index==key)
        if not len(hits): raise KeyError(key)
        return self.df._row_at(int(hits[0]))


class DataFrame:
    def __init__(self,columns,index=None):
        self._cols={str(k):np.asarray(v) for k,v in columns.items()}
        lengths={len(v) for v in self._cols.values()}
        if len(lengths)>1: raise ValueError("column length mismatch")
        n=next(iter(lengths),0)
        self.index=np.arange(n) if index is None else np.asarray(index)
        if len(self.index)!=n: raise ValueError("index length mismatch")
    def __len__(self): return len(self.index)
    def __getattr__(self,key):
        if key in self._cols:return Series(self._cols[key],self.index,key)
        raise AttributeError(key)
    def __getitem__(self,key):
        if isinstance(key,str): return Series(self._cols[key],self.index,key)
        arr=np.asarray(_as_array(key))
        if arr.dtype==bool:return self._filter(arr)
        if isinstance(key,(list,tuple)) and all(isinstance(x,str) for x in key):
            return DataFrame({x:self._cols[x] for x in key},self.index.copy())
        raise TypeError(type(key))
    @property
    def iloc(self): return _DataFrameILoc(self)
    @property
    def loc(self): return _DataFrameLoc(self)
    def copy(self): return DataFrame({k:v.copy() for k,v in self._cols.items()},self.index.copy())
    def _filter(self,mask):
        mask=np.asarray(mask,dtype=bool)
        return DataFrame({k:v[mask] for k,v in self._cols.items()},self.index[mask])
    def _row_at(self,pos): return Row(list(self._cols),[self._cols[c][pos] for c in self._cols],self.index[pos])
    def itertuples(self,index=False):
        fields=[re.sub(r'\W|^(?=\d)','_',c) for c in self._cols]
        NT=namedtuple('Pandas',fields,rename=True)
        for i in range(len(self)):
            vals=[self._cols[c][i] for c in self._cols]
            if index: yield (self.index[i],*vals)
            else: yield NT(*vals)
    def groupby(self,column,sort=False):
        vals=self._cols[column]
        order=[]
        for v in vals:
            if not any((v==x) or (isinstance(v,float) and isinstance(x,float) and np.isnan(v) and np.isnan(x)) for x in order): order.append(v)
        if sort:
            try: order=sorted(order)
            except Exception: pass
        for v in order:
            mask=(vals==v)
            yield v,self._filter(mask)


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    if not rows:return DataFrame({})
    cols={k:_parse_column([r.get(k,'') for r in rows]) for k in rows[0]}
    return DataFrame(cols)


def concat(frames,ignore_index=False):
    dfs=[]
    for x in frames:
        if isinstance(x,DataFrame):dfs.append(x)
        else:raise TypeError(type(x))
    if not dfs:return DataFrame({})
    cols=list(dfs[0]._cols)
    if any(list(d._cols)!=cols for d in dfs):raise ValueError('concat column mismatch')
    out={c:np.concatenate([d._cols[c] for d in dfs]) for c in cols}
    if ignore_index:index=np.arange(sum(len(d) for d in dfs))
    else:index=np.concatenate([d.index for d in dfs])
    return DataFrame(out,index)
