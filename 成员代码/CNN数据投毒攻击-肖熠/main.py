import torch
import random
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import matplotlib.pyplot as plt
from torchvision import datasets
from torch.utils.data import DataLoader, Subset

# 解决 Matplotlib 中文显示问题
plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

# ================= 1. 定义 AlexNet 结构 =================
class AlexNet(nn.Module):
    def __init__(self):
        super(AlexNet, self).__init__()
        # 针对 MNIST 28x28 图像进行参数调节
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.pool1 = nn.MaxPool2d(kernel_size=2, stride=2)
        self.relu1 = nn.ReLU()
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=1)
        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=2)
        self.relu2 = nn.ReLU()
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1)
        self.conv4 = nn.Conv2d(128, 256, kernel_size=3, stride=1, padding=1)
        self.conv5 = nn.Conv2d(256, 256, kernel_size=3, stride=1, padding=1)
        self.pool3 = nn.MaxPool2d(kernel_size=2, stride=2)
        self.relu3 = nn.ReLU()
        self.fc6 = nn.Linear(256 * 3 * 3, 1024)
        self.fc7 = nn.Linear(1024, 512)
        self.fc8 = nn.Linear(512, 10)

    def forward(self, x):
        x = self.conv1(x)
        x = self.pool1(x)
        x = self.relu1(x)
        x = self.conv2(x)
        x = self.pool2(x)
        x = self.relu2(x)
        x = self.conv3(x)
        x = self.conv4(x)
        x = self.conv5(x)
        x = self.pool3(x)
        x = self.relu3(x)
        x = x.view(-1, 256 * 3 * 3)
        x = self.fc6(x)
        x = F.relu(x)
        x = self.fc7(x)
        x = F.relu(x)
        x = self.fc8(x)
        return x

# ================= 2. 数据集处理函数 =================
def select_subset(dataset, ratio=1/10):
    subset_size = int(len(dataset) * ratio)
    indices = np.random.choice(range(len(dataset)), subset_size, replace=False)
    return Subset(dataset, indices)

def fetch_datasets(full_dataset, trainset, ratio):
    character = [[] for i in range(len(full_dataset.classes))]
    for index in trainset.indices:
        img, label = full_dataset[index]
        character[label].append(img)

    poison_trainset = []
    clean_trainset = []
    
    for i, data in enumerate(character):
        num_poison_train_inputs = int(len(data) * ratio[0])
        
        # 1. 注入投毒样本
        for img in data[:num_poison_train_inputs]:
            # 随机打乱标签 (0到9之间随机)
            target = random.randint(0, 9) 
            img = np.array(img)
            img = torch.from_numpy(img / 255.0).float()
            poison_trainset.append((img, target))
            
        # 2. 干净数据保持不变
        for img in data[num_poison_train_inputs:]:
            img = np.array(img)
            img = torch.from_numpy(img / 255.0).float()
            clean_trainset.append((img, i))

    return {'poisonTrain': poison_trainset, 'cleanTrain': clean_trainset}

# ================= 3. 绘图展示函数 =================
def plot_classified_images(model, dataset, device, num_images=10, is_correct=True):
    model.eval()
    imgs_to_show = []
    for img, label in dataset:
        img_tensor = img.type(torch.FloatTensor).unsqueeze(0).unsqueeze(0).to(device)
        with torch.no_grad():
            pred = model(img_tensor)
        pred_label = torch.argmax(pred).item()
        
        condition = (pred_label == label) if is_correct else (pred_label != label)
        if condition:
            imgs_to_show.append((img.cpu().squeeze(), label, pred_label))
        if len(imgs_to_show) >= num_images:
            break

    plt.figure(figsize=(10, 5))
    for i, (img, true_label, pred_label) in enumerate(imgs_to_show):
        plt.subplot(2, 5, i + 1)
        plt.imshow(img.numpy(), cmap='gray')
        plt.title(f"T:{true_label}, P:{pred_label}")
        plt.axis('off')
    title_prefix = "正确" if is_correct else "错误"
    plt.suptitle(f"投毒检测 - {title_prefix}分类示例")
    plt.tight_layout()
    plt.show()

# ================= 4. 主程序运行 =================
if __name__ == '__main__':
    # 在这里修改投毒比例！(当前为投毒 50%)
    poison_rate = 0.5   
    clean_rate = 1.0 - poison_rate

    print("正在下载并准备 MNIST 数据集...")
    trainset_all = datasets.MNIST(root='./data', download=True, train=True)
    trainset = select_subset(trainset_all, ratio=0.1) # 取 1/10 训练以加快实验速度
    
    all_datasets = fetch_datasets(full_dataset=trainset_all, trainset=trainset, ratio=[poison_rate, clean_rate])
    poison_trainset = all_datasets['poisonTrain']
    clean_trainset = all_datasets['cleanTrain']
    all_trainset = poison_trainset + clean_trainset  # 合并为最终训练集

    # 准备测试集
    clean_test_all = datasets.MNIST(root='./data', download=True, train=False)
    clean_test = select_subset(clean_test_all, ratio=0.1)
    clean_testset = []
    for img, label in clean_test:
        img = np.array(img)
        img = torch.from_numpy(img / 255.0).float()
        clean_testset.append((img, label))

    trainset_dataloader = DataLoader(dataset=all_trainset, batch_size=64, shuffle=True)

    print("----------开始模型投毒训练----------")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"当前使用计算设备: {device}")
    net = AlexNet().to(device)

    loss_fn = nn.CrossEntropyLoss().to(device)
    # 在这里修改学习率！
    optimizer = torch.optim.Adam(net.parameters(), lr=0.0001)
    
    # 在这里修改训练轮次！
    total_epoch = 10 
    
    clean_acc_list = []
    epoch_loss_list = [] # 用于记录每轮的平均 Loss
    
    for epoch in range(total_epoch):
        net.train()
        running_loss = 0.0
        for index, (imgs, labels) in enumerate(trainset_dataloader):
            imgs = imgs.unsqueeze(1).type(torch.FloatTensor).to(device)
            labels = labels.to(device)

            optimizer.zero_grad()
            outputs = net(imgs)
            loss = loss_fn(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
            
        avg_loss = running_loss / len(trainset_dataloader)
        epoch_loss_list.append(avg_loss)
        print(f"Epoch: {epoch + 1}, Loss: {avg_loss:.4f}")

        # --- 在测试集上评估 ---
        net.eval()
        clean_correct = 0
        for img, label in clean_testset:
            img_tensor = img.type(torch.FloatTensor).unsqueeze(0).unsqueeze(0).to(device)
            with torch.no_grad():
                pred = net(img_tensor)
            top_pred = torch.argmax(pred).item()
            if top_pred == label:
                clean_correct += 1
                
        clean_acc = clean_correct / len(clean_testset) * 100
        clean_acc_list.append(clean_acc)
        print(f"测试集准确率: {clean_acc:.2f}%")
        print("-" * 30)

    # ================= 5. 绘制最终图表 =================
    # 绘制准确率折线图
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    plt.plot(range(1, total_epoch + 1), clean_acc_list, label='Accuracy', marker='o', linestyle='-')
    plt.title(f'准确率曲线 (投毒比例={poison_rate*100}%)')
    plt.xlabel('训练轮数 (epoch)')
    plt.ylabel('准确率 (%)')
    plt.ylim(0, 100)
    plt.grid(True)
    plt.legend()

    # 绘制损失函数折线图 
    plt.subplot(1, 2, 2)
    plt.plot(range(1, total_epoch + 1), epoch_loss_list, label='Loss', marker='x', color='red', linestyle='--')
    plt.title(f'Loss下降曲线 (投毒比例={poison_rate*100}%)')
    plt.xlabel('训练轮数 (epoch)')
    plt.ylabel('损失值 (Loss)')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()

    # 展示正确和错误的图片
    plot_classified_images(net, clean_testset, device, num_images=10, is_correct=True)
    plot_classified_images(net, clean_testset, device, num_images=10, is_correct=False)