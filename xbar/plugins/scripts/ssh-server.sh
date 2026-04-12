#!/bin/bash
# Set SSH_SERVER_HOST in your shell env, e.g. export SSH_SERVER_HOST=user@host
sudo ssh "${SSH_SERVER_HOST:?set SSH_SERVER_HOST=user@host in your env}"
