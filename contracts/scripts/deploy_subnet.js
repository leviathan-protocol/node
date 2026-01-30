/**
 * DAHAO Contracts Deployment Script - DAHAO Subnet
 *
 * Deploys the full DAHAO governance stack to the local DAHAO Subnet:
 * 1. DAHAOForwarder - ERC2771 forwarder for meta-transactions
 * 2. DAHAOToken - ERC20Votes governance token
 * 3. DAHAOGovernor - Governance contract with gasless voting support
 *
 * Usage:
 *   # First, start the DAHAO Subnet
 *   ./scripts/setup_dahao_subnet.sh
 *
 *   # Then deploy contracts
 *   npx hardhat run scripts/deploy_subnet.js --network dahaoSubnet
 *
 * The EWOQ test account is pre-funded with 1M DAHAO native tokens for gas.
 */

const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await hre.ethers.getSigners();

  console.log("=".repeat(60));
  console.log("DAHAO Contracts Deployment - DAHAO Subnet");
  console.log("=".repeat(60));
  console.log();
  console.log(`Network: ${hre.network.name}`);
  console.log(`Chain ID: ${(await hre.ethers.provider.getNetwork()).chainId}`);
  console.log(`Deployer: ${deployer.address}`);

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`Balance: ${hre.ethers.formatEther(balance)} DAHAO`);
  console.log();

  if (balance === 0n) {
    console.error("ERROR: Deployer has no balance!");
    console.error("Make sure the DAHAO Subnet is running:");
    console.error("  ./scripts/setup_dahao_subnet.sh");
    process.exit(1);
  }

  // 1. Deploy DAHAOForwarder
  console.log("1. Deploying DAHAOForwarder...");
  const DAHAOForwarder = await hre.ethers.getContractFactory("DAHAOForwarder");
  const forwarder = await DAHAOForwarder.deploy();
  await forwarder.waitForDeployment();
  const forwarderAddress = await forwarder.getAddress();
  console.log(`   DAHAOForwarder deployed to: ${forwarderAddress}`);

  // 2. Deploy DAHAOToken
  console.log("2. Deploying DAHAOToken...");
  const DAHAOToken = await hre.ethers.getContractFactory("DAHAOToken");
  const token = await DAHAOToken.deploy(deployer.address);
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log(`   DAHAOToken deployed to: ${tokenAddress}`);

  // Verify token details
  const tokenName = await token.name();
  const tokenSymbol = await token.symbol();
  const totalSupply = await token.totalSupply();
  console.log(`   Token: ${tokenName} (${tokenSymbol})`);
  console.log(`   Total Supply: ${hre.ethers.formatEther(totalSupply)} DAHAO`);

  // 3. Deploy DAHAOGovernor
  console.log("3. Deploying DAHAOGovernor...");
  const DAHAOGovernor = await hre.ethers.getContractFactory("DAHAOGovernor");
  const governor = await DAHAOGovernor.deploy(tokenAddress, forwarderAddress);
  await governor.waitForDeployment();
  const governorAddress = await governor.getAddress();
  console.log(`   DAHAOGovernor deployed to: ${governorAddress}`);

  // Verify governor settings
  const votingDelay = await governor.votingDelay();
  const votingPeriod = await governor.votingPeriod();
  console.log(`   Voting Delay: ${votingDelay} seconds (~${Number(votingDelay) / 86400} days)`);
  console.log(`   Voting Period: ${votingPeriod} seconds (~${Number(votingPeriod) / 86400} days)`);

  // 4. Delegate tokens to deployer for voting power
  console.log("4. Delegating tokens to deployer for voting power...");
  const delegateTx = await token.delegate(deployer.address);
  await delegateTx.wait();
  const votingPower = await token.getVotes(deployer.address);
  console.log(`   Voting power: ${hre.ethers.formatEther(votingPower)} DAHAO`);

  // Summary
  console.log();
  console.log("=".repeat(60));
  console.log("Deployment Summary");
  console.log("=".repeat(60));
  console.log();
  console.log("Contract Addresses:");
  console.log(`  DAHAOForwarder: ${forwarderAddress}`);
  console.log(`  DAHAOToken:     ${tokenAddress}`);
  console.log(`  DAHAOGovernor:  ${governorAddress}`);
  console.log();

  // Generate config for Python sidecar
  const chainId = (await hre.ethers.provider.getNetwork()).chainId;
  const rpcUrl = hre.network.config.url;

  const configYaml = `# DAHAO Subnet Configuration (Auto-generated)
# Generated at: ${new Date().toISOString()}
#
# Start subnet first: ./scripts/setup_dahao_subnet.sh

chain:
  type: evm
  chain_id: "${chainId}"
  rpc_url: "${rpcUrl}"
  governor_address: "${governorAddress}"
  token_address: "${tokenAddress}"
  forwarder_address: "${forwarderAddress}"
  gas_limit: 200000

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"
  n_ctx: 8192

sidecar:
  poll_interval_seconds: 60
  max_retries: 3
  state_file: "sidecar_state.json"
  decisions_log: "decisions.log"

# Environment variables needed:
#   RELAYER_PRIVATE_KEY=56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027
`;

  // Write config file
  const configPath = path.join(__dirname, "..", "..", "config_dahao_subnet.yaml");
  fs.writeFileSync(configPath, configYaml);
  console.log(`Config written to: ${configPath}`);
  console.log();

  // Output usage instructions
  console.log("=".repeat(60));
  console.log("Ready to Use!");
  console.log("=".repeat(60));
  console.log();
  console.log("Set relayer private key (EWOQ test key):");
  console.log("  export RELAYER_PRIVATE_KEY=56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027");
  console.log();
  console.log("Start Observer Mode:");
  console.log("  python main.py --mode observer --config config_dahao_subnet.yaml");
  console.log();
  console.log("Test connection:");
  console.log(`  curl ${rpcUrl} -X POST -H "Content-Type: application/json" --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}'`);
  console.log();

  // Also write a JSON file for programmatic access
  const deploymentInfo = {
    network: hre.network.name,
    chainId: chainId.toString(),
    rpcUrl: rpcUrl,
    deployer: deployer.address,
    contracts: {
      forwarder: forwarderAddress,
      token: tokenAddress,
      governor: governorAddress,
    },
    deployedAt: new Date().toISOString(),
  };

  const deploymentPath = path.join(__dirname, "..", "deployments", "dahao_subnet.json");
  fs.mkdirSync(path.dirname(deploymentPath), { recursive: true });
  fs.writeFileSync(deploymentPath, JSON.stringify(deploymentInfo, null, 2));
  console.log(`Deployment info saved to: ${deploymentPath}`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
