#!/bin/sh

# helper script to generate a key pair to sign/verify RS256 JWTs

PRIV_KEY=jwt_private_key.pem
PUB_KEY=jwt_public_key.pem
SECRET=secret

set -e

openssl genpkey -algorithm RSA -out ${PRIV_KEY} -pass pass:${SECRET}

openssl rsa -pubout -in ${PRIV_KEY} -out ${PUB_KEY} -passin pass:${SECRET}
