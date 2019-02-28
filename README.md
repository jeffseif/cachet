# cachet

Unburden your functions and grant them the **cachet** they deserve ... with caches!

## Install to the system

```bash
pip install -e git+https://github.com/jeffseif/cachet.git#egg=cachet
```

## Use in a package

```diff
diff --git a/requirements.txt b/requirements.txt
index 762212b..545d0cf 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,3 +1,4 @@
+-e git://github.com/jeffseif/cachet.git#egg=cachet
diff --git a/setup.py b/setup.py
index 6b12258..cb27369 100644
--- a/setup.py
+++ b/setup.py
@@ -10,6 +10,9 @@ from switch import __version__
 setup(
+    dependency_links=[
+        'https://github.com/jeffseif/cachet.git#egg=cachet',
+    ],
```

```python
>>> from time import time
>>> from cachet import dict_cache
>>> cached_time = dict_cache(ttl=1)(time)
>>> cached_time()
1551331720.1623466
>>> cached_time()
1551331720.1623466
>>> cached_time()
1551331721.3898005
>>> cached_time()
1551331721.3898005
```
