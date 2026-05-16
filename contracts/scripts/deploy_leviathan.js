// scripts/deploy_leviathan.js
// Deploy full Leviathan testnet: Token + QuestBoard + Reputation

const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  
  console.log("═══════════════════════════════════════════════════════════");
  console.log("🐙 LEVIATHAN TESTNET DEPLOYMENT");
  console.log("═══════════════════════════════════════════════════════════");
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Balance: ${hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address))} AVAX`);
  console.log("");

  // 1. Deploy Token ($LVTN)
  console.log("1️⃣  Deploying LeviathanToken...");
  const Token = await hre.ethers.getContractFactory("LeviathanToken");
  const token = await Token.deploy(deployer.address);
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log(`   ✅ Token deployed: ${tokenAddress}`);
  console.log(`   💰 Total Supply: 1,000,000,000 LVTN`);
  console.log("");

  // 2. Deploy Reputation (Passport)
  console.log("2️⃣  Deploying Reputation...");
  const Reputation = await hre.ethers.getContractFactory("Reputation");
  const reputation = await Reputation.deploy(deployer.address);
  await reputation.waitForDeployment();
  const reputationAddress = await reputation.getAddress();
  console.log(`   ✅ Reputation deployed: ${reputationAddress}`);
  console.log("");

  // 3. Deploy QuestBoard (Job Market)
  console.log("3️⃣  Deploying QuestBoard...");
  const QuestBoard = await hre.ethers.getContractFactory("QuestBoard");
  const questBoard = await QuestBoard.deploy(
    tokenAddress,           // Reward token
    deployer.address,       // Treasury (deployer for testnet)
    deployer.address        // Owner
  );
  await questBoard.waitForDeployment();
  const questBoardAddress = await questBoard.getAddress();
  console.log(`   ✅ QuestBoard deployed: ${questBoardAddress}`);
  console.log("");

  // 4. Setup connections
  console.log("4️⃣  Configuring contracts...");
  
  // Connect QuestBoard to Reputation
  await questBoard.setReputationContract(reputationAddress);
  console.log("   ✅ QuestBoard → Reputation linked");
  
  // Authorize QuestBoard to modify Reputation
  await reputation.addAuthorizedCaller(questBoardAddress);
  console.log("   ✅ QuestBoard authorized to update Reputation");
  
  // Add deployer as validator (for testnet)
  await questBoard.addValidator(deployer.address);
  console.log("   ✅ Deployer added as validator");
  console.log("");

  // 5. Seed with initial quest (optional demo)
  console.log("5️⃣  Creating demo quest...");
  
  // Approve QuestBoard to spend tokens
  const bounty = hre.ethers.parseEther("1000"); // 1000 LVTN
  await token.approve(questBoardAddress, bounty);
  
  // Create a demo quest
  const deadline = Math.floor(Date.now() / 1000) + (7 * 24 * 60 * 60); // 1 week
  await questBoard.createQuest(
    "security",
    "Audit the DAHAO Protocol smart contracts for vulnerabilities",
    bounty,
    deadline,
    100 // XP reward
  );
  console.log("   ✅ Demo quest created: 1000 LVTN bounty");
  console.log("");

  // Summary
  console.log("═══════════════════════════════════════════════════════════");
  console.log("🎉 DEPLOYMENT COMPLETE");
  console.log("═══════════════════════════════════════════════════════════");
  console.log("");
  console.log("Contract Addresses:");
  console.log(`  Token (LVTN):  ${tokenAddress}`);
  console.log(`  Reputation:    ${reputationAddress}`);
  console.log(`  QuestBoard:    ${questBoardAddress}`);
  console.log("");
  console.log("Configuration:");
  console.log(`  Treasury:      ${deployer.address}`);
  console.log(`  Validator:     ${deployer.address}`);
  console.log(`  Protocol Fee:  5%`);
  console.log(`  Node Fee:      10%`);
  console.log("");
  
  // Save deployment info
  const deployment = {
    network: hre.network.name,
    deployer: deployer.address,
    timestamp: new Date().toISOString(),
    contracts: {
      token: tokenAddress,
      reputation: reputationAddress,
      questBoard: questBoardAddress
    },
    config: {
      treasury: deployer.address,
      validator: deployer.address,
      protocolFee: "5%",
      nodeFee: "10%"
    }
  };
  
  const fs = require("fs");
  const path = require("path");
  const deploymentPath = path.join(__dirname, "..", "deployments", `${hre.network.name}.json`);
  fs.writeFileSync(deploymentPath, JSON.stringify(deployment, null, 2));
  console.log(`📁 Deployment saved to: ${deploymentPath}`);
  console.log("");
  console.log("Next Steps:");
  console.log("  1. Start validator node: python node/validator.py");
  console.log("  2. Update website with contract addresses");
  console.log("  3. Test quest flow end-to-end");
  console.log("═══════════════════════════════════════════════════════════");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
