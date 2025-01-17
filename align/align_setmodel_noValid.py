import time
import torch
import torch.optim as optim
from tensorboardX import SummaryWriter

from autil import alignment2
from align import align_model2, align_setmodel2


class modelClass2():
    def __init__(self, config, myprint_fun):
        super(modelClass2, self).__init__()

        self.myprint = myprint_fun  # Printing and logging
        self.config = config
        self.best_mode_pkl_title = config.output + time.strftime('%Y-%m-%d_%H_%M_%S-', time.localtime(time.time()))

        # Load data
        input_data = align_setmodel2.load_data(config)
        # train、Valid、Test
        self.train_links = input_data.train_links
        # self.test_links = input_data.test_links
        self.train_links_tensor = input_data.train_links_tensor
        self.test_links_tensor = input_data.test_links_tensor
        print(self.test_links_tensor.size(),'1111111')
        # Model and optimizer  【HET_align】
        self.mymodel = align_model2.HET_align2(input_data, config)

        if config.cuda:
            self.mymodel.cuda()
        # [TensorboardX]Summary_Writer
        self.board_writer = SummaryWriter(log_dir=self.best_mode_pkl_title + '-E/', comment='HET_align')

        # optimizer
        self.parameters = filter(lambda p: p.requires_grad, self.mymodel.parameters())
        self.myprint('All parameter names in the model:' + str(len(self.mymodel.state_dict())))
        for i in self.mymodel.state_dict():
            self.myprint(i)
        if config.optim_type == 'Adagrad':
            self.optimizer = optim.Adam(self.parameters, lr=config.learning_rate,
                            weight_decay=config.weight_decay)  # weight_decay =5e-4
        else:
            self.optimizer = optim.SGD(self.parameters, lr=config.learning_rate,
                            weight_decay=config.weight_decay)
        # Weight initialization Weight initialization
        self.mymodel.init_weights()

    ## model train
    def model_train(self, epochs_beg=0):
        self.myprint("model training start==" + time.strftime('%Y.%m.%d %H:%M:%S', time.localtime(time.time())))
        t_begin = time.time()

        #
        bad_counter = 0
        best_hits1 = 0  # best
        best_epochs = 0
        for epochs_i in range(epochs_beg, self.config.train_epochs):  # epochs=1001
            epochs_i_t = time.time()
            #  Forward pass
            self.mymodel.train()
            
            e_out_embed = self.mymodel()
            print(e_out_embed.size(),'444444444444444444')
            self.regen_neg(epochs_i, e_out_embed)

            # loss、acc
            loss_train = self.mymodel.get_loss(e_out_embed, self.train_neg_pairs)  # 求解loss:
            # Backward and optimize
            self.optimizer.zero_grad()
            loss_train.backward()
            self.optimizer.step()

            if epochs_i % 5 != 0:
                self.myprint('Epoch-{:04d}: train_loss-{:.4f}, cost time-{:.4f}s'.format(
                    epochs_i, loss_train.data.item(), time.time() - epochs_i_t))
            else:
                # accuracy: hits, mr, mrr
                result_train = alignment2.my_accuracy(e_out_embed, self.train_links_tensor,
                                                      metric=self.config.metric, top_k=self.config.top_k)

                # [TensorboardX]
                self.board_writer.add_scalar('train_loss', loss_train.data.item(), epochs_i)
                self.board_writer.add_scalar('train_hits1', result_train[0][0], epochs_i)

                self.myprint('Epoch-{:04d}: train_loss-{:.4f}, cost time-{:.4f}s'.format(
                    epochs_i, loss_train.data.item(), time.time() - epochs_i_t))
                self.print_result('Train', result_train)

            # # ********************no early stop********************************************
            if epochs_i >= self.config.start_valid and epochs_i % self.config.eval_freq == 0:
                # From left
                result_test = alignment2.my_accuracy(e_out_embed, self.test_links_tensor, top_k=self.config.top_k,
                                                     metric=self.config.metric)
                                                     
                self.print_result('Temp Test From Left', result_test)

                # save best model in valid
                if result_test[0][0] >= best_hits1:
                    best_hits1 = result_test[0][0]
                    best_epochs = epochs_i
                    bad_counter = 0
                    self.myprint('Epoch-{:04d}, better result, best_hits1:{:.4f}..'.format(epochs_i, best_hits1))
                    self.save_model(epochs_i, 'best-epochs')  # 保存最好的模型
                else:
                    # no best, but save model every 50 epochs
                    if epochs_i % self.config.eval_save_freq == 0:
                        self.save_model(epochs_i, 'eval-epochs')
                    # bad model, stop train
                    bad_counter += 1
                    self.myprint('bad_counter++:' + str(bad_counter))
                    if bad_counter == self.config.patience:  # patience=20
                        self.myprint('Epoch-{:04d},bad_counter.'.format(epochs_i))
                        break

        self.save_model(epochs_i, 'last-epochs')  # save last epochs
        self.myprint("Optimization Finished!")
        self.myprint('Best epoch-{:04d}:'.format(best_epochs))
        self.myprint('Last epoch-{:04d}:'.format(epochs_i))
        self.myprint("Total time elapsed: {:.4f}s".format(time.time() - t_begin))

        return best_epochs, epochs_i


    # get negative samples
    def regen_neg(self, epochs_i, ent_embed):
        if epochs_i % self.config.sample_neg_freq == 0:  # sample negative pairs every 20 epochs
            with torch.no_grad():
                # Negative sample sampling-training pair (positive sample and negative sample)
                self.train_neg_pairs = alignment2.gen_neg(ent_embed, self.train_links, self.config.metric, self.config.neg_k)


    def compute_test(self, epochs_i, name_epochs):
        ''' run best model '''
        model_savefile = '{}-epochs{}-{}.pkl'.format(self.best_mode_pkl_title + name_epochs, epochs_i, self.config.model_param)
        self.myprint('\nLoading {} - {}th epoch'.format(name_epochs, epochs_i))
        self.re_test(model_savefile)


    def re_test(self, model_savefile):
        ''' restart run best model '''
        # Restore best model
        self.myprint('Loading file: ' + model_savefile)
        self.mymodel.load_state_dict(torch.load(model_savefile))
        self.mymodel.eval()  # self.train(False)
        e_out_embed_test = self.mymodel()
        

        # From left
        result_test = alignment2.my_accuracy(e_out_embed_test, self.test_links_tensor, top_k=self.config.top_k,
                                                    metric=self.config.metric)
        result_str1 = self.print_result('Test From Left', result_test)
        # From right
        result_test = alignment2.my_accuracy(e_out_embed_test, self.test_links_tensor, top_k=self.config.top_k,
                                                    metric=self.config.metric, fromLeft=False)
        result_str2 = self.print_result('Test From right', result_test)

        model_result_file = '{}_Result-{}.txt'.format(self.best_mode_pkl_title, self.config.model_param)
        with open(model_result_file, "a") as ff:
            ff.write(result_str1)
            ff.write('\n')
            ff.write(result_str2)
            ff.write('\n')


    def save_model(self, better_epochs_i, epochs_name):  # best-epochs
        # save model to file
        model_savefile = self.best_mode_pkl_title + epochs_name + \
                         str(better_epochs_i) + '-' + self.config.model_param + '.pkl'
        torch.save(self.mymodel.state_dict(), model_savefile)


    def print_result(self, pt_type, run_re):
        ''' Output result '''
        hits, mr, mrr = run_re[0], run_re[1], run_re[2]
        result = pt_type
        result += "==results: hits@{} = {}%, mr = {:.3f}, mrr = {:.6f}".format(self.config.top_k, hits, mr, mrr)
        self.myprint(result)
        return result



