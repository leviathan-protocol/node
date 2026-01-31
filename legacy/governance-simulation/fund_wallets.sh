#!/bin/bash
# Fund all simulation wallets from the alice account
# Run this while the chain is running: cd dahao && ignite chain serve

set -e

export PATH=$PATH:~/go/bin

echo "Funding simulation wallets..."

echo "Funding Alice..."
dahaod tx bank send alice cosmos1an6syc50wstcualuexqfkungaw6jswm5vsl4dj 10000000stake --yes --keyring-backend test

sleep 2

echo "Funding Bob..."
dahaod tx bank send alice cosmos14c9muh09vexe947nuwyv5xy5tmnwez68he2z9f 10000000stake --yes --keyring-backend test

sleep 2

echo "Funding Charlie..."
dahaod tx bank send alice cosmos1skvg6qkkg6x0uuc8e9zld47j2umjx0uz92s6nv 10000000stake --yes --keyring-backend test

sleep 2

echo "Funding Dave..."
dahaod tx bank send alice cosmos1tkyts2q8ne56w7lhfvvn4g4g00g50gt7cqcuep 10000000stake --yes --keyring-backend test

sleep 2

echo "Funding Eve..."
dahaod tx bank send alice cosmos18q6z7dsguuu3qndqjcm3fju33vzfuh33vu52n8 10000000stake --yes --keyring-backend test

echo ""
echo "All wallets funded!"
echo ""
echo "You can now run: python simulation_swarm.py"
