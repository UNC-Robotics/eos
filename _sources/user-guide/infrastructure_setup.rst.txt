Infrastructure Setup
====================

EOS requires setting up a network infrastructure to securely access laboratory devices and computers, which are defined
in a :doc:`laboratory YAML file <laboratories>`.

Key Requirements
----------------

#. Use an isolated or properly firewalled LAN to prevent unauthorized access
#. Place all controlled laboratory computers in the same LAN and assign them static IP addresses
#. Configure firewalls to allow bi-directional network access on all ports between EOS and laboratory computers
#. Adjust power management settings to prevent computer hibernation during long automation runs

.. figure:: ../_static/img/lab-lan.png
   :alt: Example LAN setup for EOS
   :scale: 75%
   :align: center