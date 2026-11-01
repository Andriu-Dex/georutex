FROM odoo:16.0

USER root

# Install development and testing dependencies in the test image
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements-dev.txt

USER odoo

