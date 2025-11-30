.. _gettingstarted/installations/shinken-installation:

=====================================
10 Minutes Shinken Installation Guide 
=====================================


Summary 
=======

By following this tutorial, in 10 minutes you will have the core monitoring system for your network.

The very first step is to verify that your server meets the :ref:`requirements <gettingstarted/installations/shinken-installation#requirements>`, the installation script will try to meet all requirements automatically.
   
You can get familiar with the :ref:`Shinken Architecture <architecture/the-shinken-architecture>` now, or after the installation. This will explain the software components and how they fit together.

  * Installation : :ref:`GNU/Linux & Unix <gettingstarted/installations/shinken-installation#gnu_linux_unix>`
  * Installation : :ref:`Windows <gettingstarted/installations/shinken-installation#windows_installation>`

Ready? Let's go!


.. _gettingstarted/installations/shinken-installation#requirements:

Requirements
============

Mandatory Requirements
----------------------

* `Python`_ 3.8 or higher (tested with Python 3.13)
* `python-pycurl`_ Python package for Shinken daemon communication
* `CherryPy`_ for the embedded web server
* `setuptools`_ and `pip` Python packages for installation


Conditional Requirements
------------------------

* `Monitoring Plugins`_ (recommended) provides a set of plugins to monitor host (Shinken uses check_icmp by default install).
  Monitoring plugins are available on most linux distributions (nagios-plugins package)


.. _gettingstarted/installations/shinken-installation#gnu_linux_unix:

.. warning::  Do not mix installation methods! If you wish to change method, use the uninstaller from the chosen method THEN install using the alternate method.


GNU/Linux & Unix Installation 
=============================

Method 1: Pip
-------------

Shinken 2.4 is available on Pypi : https://pypi.python.org/pypi/Shinken/2.4
You can download the tarball and execute the setup.py or just use the pip command to install it automatically.


::

  apt-get install python3-pip python3-pycurl
  adduser shinken
  pip install shinken


Fedora 42 (Python 3.13)
-----------------------

On Fedora 42, Shinken can be installed in an isolated Python 3.13 virtual environment while keeping
system tools untouched. The following commands install compiler dependencies required by ``pycurl``,
set up a virtual environment and install Shinken with the Python 3 packages declared in this
repository:

.. code-block:: bash

  sudo dnf install python3.13 python3.13-pip python3.13-devel libcurl-devel libffi-devel \
       openssl-devel gcc make
  sudo useradd --system --create-home --shell /sbin/nologin shinken
  python3.13 -m venv /opt/shinken
  source /opt/shinken/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  pip install .

If you plan to manage Shinken as a service, copy the generated scripts from ``/opt/shinken/bin``
into a directory on the global ``PATH`` (for example ``/usr/local/bin``) and create a systemd unit
that activates the virtual environment before launching ``shinken --validate``.


.. notice:: Depending on your distribution, you may need to explicitly tell pip where to install the executables. For example on Ubuntu you should use ``pip install shinken --install-option="--install-scripts=/usr/local/bin"``.

Method 2: Packages 
-------------------

For now the 2.4 packages are not available, but the community is working hard for it! Packages are simple, easy to update and clean.
Packages should be available on Debian/Ubuntu and Fedora/RH/CentOS soon (basically  *.deb* and  *.rpm*).


Method 3: Installation from sources 
------------------------------------

Download last stable `Shinken tarball`_ archive (or get the latest `git snapshot`_) and extract it somewhere:

::

  adduser shinken
  wget http://www.shinken-monitoring.org/pub/shinken-2.4.tar.gz
  tar -xvzf shinken-2.4.tar.gz
  cd shinken-2.4
  python setup.py install


Shinken 2.X uses LSB path. If you want to stick to one directory installation you can of course.
Default paths are the following:

 * **/etc/shinken** for configuration files
 * **/var/lib/shinken** for shinken modules, retention files...
 * **/var/log/shinken** for log files
 * **/var/run/shinken** for pid files


.. _gettingstarted/installations/shinken-installation#windows_installation:


Windows Installation 
====================

For 2.X+ the executable installer may not be provided. Consequently, installing Shinken on a Windows may be manual with setup.py.
Steps are basically the same as on Linux (Python install etc.) but in windows environment it's always a bit tricky.


.. _Python: http://www.python.org/download/
.. _python-cherrypy3: http://www.cherrypy.org/
.. _CherryPy: https://cherrypy.dev/
.. _Monitoring Plugins: https://www.monitoring-plugins.org/
.. _python-pycurl: http://pycurl.sourceforge.net/
.. _setuptools: http://pypi.python.org/pypi/setuptools/
.. _git snapshot: https://github.com/naparuba/shinken/tarball/master
.. _Shinken tarball: http://www.shinken-monitoring.org/pub/shinken-2.4.tar.gz
.. _install.d/README: https://github.com/naparuba/shinken/blob/master/install.d/README

